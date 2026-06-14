from __future__ import annotations

import contextlib
import importlib.util
import sys
import typing as t
from pathlib import Path

import numpy as np
import panel as pn
import pytest
from panel.tests.conftest import port, server_cleanup  # noqa: F401
from panel.tests.util import serve_and_wait

import holoviews as hv

if t.TYPE_CHECKING:
    from collections.abc import Callable

# ---------------------------------------------------------------------------
# Load workflow map — single source of truth for marker definitions.
# The map lives in scripts/workflow_map.py and is shared by conftest,
# pixi tasks, CI, and developer documentation.
# Run `python scripts/workflow_sync.py check` to verify all layers are in sync.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_MAP_PATH = _PROJECT_ROOT / "scripts" / "workflow_map.py"

if _WORKFLOW_MAP_PATH.exists():
    _spec = importlib.util.spec_from_file_location("workflow_map", _WORKFLOW_MAP_PATH)
    _workflow_map = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_workflow_map)
    _GROUPS = _workflow_map.GROUPS
    _MARKERS = _workflow_map.get_all_markers()
    _EXCLUDED_BY_DEFAULT = _workflow_map.get_excluded_by_default_markers()
else:
    # Fallback: static list (kept in sync by workflow_sync.py --check)
    _MARKERS = (
    "core",
    "datashader",
    "gpu",
    "ipython",
    "operation",
    "plotting",
    "plotting_bokeh",
    "plotting_mpl",
    "plotting_plotly",
    "ui",
)
    _EXCLUDED_BY_DEFAULT = ("ui", "gpu")
    _GROUPS = None


def pytest_addoption(parser):
    for marker in _MARKERS:
        parser.addoption(
            f"--{marker.replace('_', '-')}",
            action="store_true",
            default=False,
            help=f"Run {marker} related tests",
        )


def pytest_configure(config):
    if _GROUPS is not None:
        for group in _GROUPS:
            config.addinivalue_line("markers", f"{group.marker}: {group.description}")
    else:
        for marker in _MARKERS:
            config.addinivalue_line("markers", f"{marker}: {marker} test marker")


def pytest_collection_modifyitems(config, items):
    """
    Filter and mark tests based on the workflow map (single source of truth).

    Two mechanisms work together:
    1. Dynamic marking: if workflow_map.py is available, markers are applied
       to each test item based on its file path (no hard-coded pytestmark needed).
    2. CLI flag filtering: --<marker-name> flags select only tests with that marker.
       By default, markers in EXCLUDED_BY_DEFAULT (ui, gpu) are skipped.

    Note: This is independent of pytest's built-in -m / -k filtering,
    which can still be combined (e.g. pytest -m plotting_bokeh -k raster).
    """
    tests_dir = Path(__file__).resolve().parent  # holoviews/tests/

    # Step 1: Apply dynamic markers based on file path (from workflow map)
    if _GROUPS is not None:
        for item in items:
            rel_path = str(Path(item.path).resolve().relative_to(tests_dir))
            for group in _GROUPS:
                if _workflow_map.file_matches_group(rel_path, group):
                    item.add_marker(group.marker)
                    for also in group.also_markers:
                        item.add_marker(also)

    # Step 2: Filter based on CLI flags
    requested = []
    for marker in _MARKERS:
        if config.getoption(marker):
            requested.append(marker)

    if not requested:
        excluded = _EXCLUDED_BY_DEFAULT
        skipped = [item for item in items if any(m in item.keywords for m in excluded)]
        selected = [item for item in items if item not in skipped]
    else:
        selected = [item for item in items if any(m in item.keywords for m in requested)]
        skipped = [item for item in items if item not in selected]

    config.hook.pytest_deselected(items=skipped)
    items[:] = sorted(selected, key=lambda x: x.path)


with contextlib.suppress(ImportError):
    import matplotlib as mpl

    mpl.use("agg")


@pytest.fixture
def ibis_sqlite_backend():
    try:
        import ibis
    except ImportError:
        yield None
    else:
        ibis.set_backend("sqlite")
        yield
        ibis.set_backend(None)


def _plotting_backend(backend):
    pytest.importorskip(backend)
    if not hv.extension._loaded:
        hv.extension(backend)
    hv.renderer(backend)
    current_backend = hv.Store.current_backend
    hv.Store.set_current_backend(backend)
    yield
    hv.Store.set_current_backend(current_backend)


@pytest.fixture
def bokeh_backend():
    yield from _plotting_backend("bokeh")


@pytest.fixture
def mpl_backend():
    yield from _plotting_backend("matplotlib")


@pytest.fixture
def plotly_backend():
    yield from _plotting_backend("plotly")


@pytest.fixture
def unimport(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    """
    Return a function for unimporting modules and preventing reimport.

    This will block any new modules from being imported.
    """

    def unimport_module(modname: str) -> None:
        # Remove if already imported
        monkeypatch.delitem(sys.modules, modname, raising=False)
        items = [m for m in sys.modules if m.startswith(f"{modname}.")]
        for item in items:
            monkeypatch.delitem(sys.modules, item, raising=False)
        # Prevent import:
        monkeypatch.setattr(sys, "path", [])

    return unimport_module


@pytest.fixture
def serve_hv(page, port):  # noqa: F811
    def serve_and_return_page(hv_obj):
        serve_and_wait(pn.pane.HoloViews(hv_obj), port=port)
        page.goto(f"http://localhost:{port}")
        return page

    return serve_and_return_page


@pytest.fixture
def serve_panel(page, port):  # noqa: F811
    def serve_and_return_page(pn_obj):
        serve_and_wait(pn.panel(pn_obj), port=port)
        page.goto(f"http://localhost:{port}")
        return page

    return serve_and_return_page


@pytest.fixture(autouse=True, scope="module")
def reset_store():
    _custom_options = {k: {} for k in hv.Store._custom_options}
    _options = hv.Store._options.copy()
    current_backend = hv.Store.current_backend
    renderers = hv.Store.renderers.copy()
    yield
    hv.Store._custom_options = _custom_options
    hv.Store._options = _options
    hv.Store._weakrefs = {}
    hv.Store.renderers = renderers
    hv.Store.set_current_backend(current_backend)


@pytest.fixture
def rng():
    return np.random.default_rng(1)
