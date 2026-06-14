from __future__ import annotations

import contextlib
import sys
import typing as t

import numpy as np
import panel as pn
import pytest
from panel.tests.conftest import port, server_cleanup  # noqa: F401
from panel.tests.util import serve_and_wait

import holoviews as hv

if t.TYPE_CHECKING:
    from collections.abc import Callable

CUSTOM_MARKS = (
    "ui",
    "gpu",
    "core",
    "plotting",
    "plotting_bokeh",
    "plotting_mpl",
    "plotting_plotly",
    "ipython",
    "datashader",
    "operation",
)

EXCLUDED_BY_DEFAULT = ("ui", "gpu")


def pytest_addoption(parser):
    for marker in CUSTOM_MARKS:
        parser.addoption(
            f"--{marker.replace('_', '-')}",
            action="store_true",
            default=False,
            help=f"Run {marker} related tests",
        )


def pytest_configure(config):
    markers = {
        "ui": "Browser-based UI tests using Playwright",
        "gpu": "GPU-accelerated tests requiring CUDA",
        "core": "Core data structure and logic tests (core/, element/, util/, testing/)",
        "plotting": "All plotting/rendering backend tests",
        "plotting_bokeh": "Bokeh plotting backend tests (plotting/bokeh/)",
        "plotting_mpl": "Matplotlib plotting backend tests (plotting/matplotlib/)",
        "plotting_plotly": "Plotly plotting backend tests (plotting/plotly/)",
        "ipython": "IPython notebook and display hook tests (ipython/)",
        "datashader": "Datashader-related operation tests",
        "operation": "All operation tests including datashader (operation/)",
    }
    for marker in CUSTOM_MARKS:
        config.addinivalue_line("markers", f"{marker}: {markers.get(marker, marker + ' test marker')}")


def pytest_collection_modifyitems(config, items):
    """
    Filter tests based on custom --marker CLI flags.

    Default behavior (no flags): run all tests EXCEPT those marked ui/gpu.
    With --<marker> flags: run ONLY tests matching ANY of the specified markers.

    Note: This is independent of pytest's built-in -m / -k filtering,
    which can still be combined (e.g. pytest -m plotting_bokeh -k raster).
    """
    requested = []
    for marker in CUSTOM_MARKS:
        if config.getoption(marker):
            requested.append(marker)

    if not requested:
        excluded = EXCLUDED_BY_DEFAULT
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
