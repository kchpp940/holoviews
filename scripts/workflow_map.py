"""
Single Source of Truth (SSOT) for HoloViews developer workflow groups.

This file defines which test files belong to which logical group,
along with their corresponding pytest marker name, description,
and the pixi environment(s) needed to run them.

All other layers (conftest.py dynamic markers, pixi tasks, CI jobs,
developer documentation) derive from this map. If you change anything
here, run `python scripts/workflow_sync.py check` to verify consistency,
or `python scripts/workflow_sync.py sync` to auto-update derived artifacts.

Group → marker mapping:
  - Each group has one primary pytest marker (e.g. "core", "plotting_bokeh")
  - A test file can belong to multiple groups (e.g. test_datashader.py
    is both "operation" and "datashader")

Path matching rules (applied in order, first match wins for primary marker;
all matching markers are applied to each file):
  - Strings are matched as "contains" against the test file path relative
    to holoviews/tests/
  - Order matters: more specific patterns come first
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class WorkflowGroup:
    """A logical group of tests that share a marker, a pixi task, and docs."""

    name: str
    marker: str
    description: str
    paths: list[str] = field(default_factory=list)
    """List of path fragments (relative to holoviews/tests/) that belong to this group.
    A test file matches if any fragment is contained in its path."""

    also_markers: list[str] = field(default_factory=list)
    """Additional markers to apply to files in this group
    (e.g. all plotting_bokeh files also get the 'plotting' marker)."""

    default_env: str = "default"
    """The default pixi environment name used to run these tests."""

    pixi_task_override: str | None = None
    """Optional override for the pixi task name (default: test-<name>)."""

    excluded_by_default: bool = False
    """If True, these tests are skipped unless explicitly requested via --<marker> flag."""


# =====================================================================
# Group definitions — the single source of truth
# Order matters: more specific paths come first.
# =====================================================================

GROUPS: list[WorkflowGroup] = [
    # ── Core / unit tests ──────────────────────────────────────────
    WorkflowGroup(
        name="core",
        marker="core",
        description="Core data structure and logic tests (core/, element/, util/, testing/)",
        paths=[
            "core/",
            "element/",
            "util/",
            "testing/",
            "test_annotators.py",
            "test_selection.py",
            "test_streams.py",
            "test_all.py",
        ],
        pixi_task_override="test-unit-core",
        default_env="test-314",
    ),
    # ── Plotting backends ──────────────────────────────────────────
    WorkflowGroup(
        name="plotting_bokeh",
        marker="plotting_bokeh",
        description="Bokeh plotting backend tests (plotting/bokeh/)",
        paths=["plotting/bokeh/"],
        also_markers=["plotting"],
        default_env="test-314",
    ),
    WorkflowGroup(
        name="plotting_mpl",
        marker="plotting_mpl",
        description="Matplotlib plotting backend tests (plotting/matplotlib/)",
        paths=["plotting/matplotlib/"],
        also_markers=["plotting"],
        default_env="test-314",
    ),
    WorkflowGroup(
        name="plotting_plotly",
        marker="plotting_plotly",
        description="Plotly plotting backend tests (plotting/plotly/)",
        paths=["plotting/plotly/"],
        also_markers=["plotting"],
        default_env="test-314",
    ),
    WorkflowGroup(
        name="plotting",
        marker="plotting",
        description="Plotting root tests (comms, plotutils, renderclass)",
        paths=[
            "plotting/test_comms.py",
            "plotting/test_plotutils.py",
            "plotting/test_renderclass.py",
        ],
        default_env="test-314",
    ),
    # ── IPython / notebook display ────────────────────────────────
    WorkflowGroup(
        name="ipython",
        marker="ipython",
        description="IPython notebook and display hook tests (ipython/)",
        paths=["ipython/"],
        default_env="test-314",
    ),
    # ── Operations & datashader ───────────────────────────────────
    WorkflowGroup(
        name="datashader",
        marker="datashader",
        description="Datashader-related tests (datashader + downsample + decollation)",
        paths=[
            "operation/test_datashader.py",
            "operation/test_downsample.py",
            "core/test_decollation.py",
        ],
        also_markers=["operation"],
        default_env="test-314",
    ),
    WorkflowGroup(
        name="operation",
        marker="operation",
        description="All operation tests (operation/)",
        paths=["operation/"],
        default_env="test-314",
    ),
    # ── UI / Playwright ───────────────────────────────────────────
    WorkflowGroup(
        name="ui",
        marker="ui",
        description="Browser-based UI tests using Playwright",
        paths=["ui/"],
        default_env="test-ui",
        excluded_by_default=True,
    ),
    # ── GPU / CUDA ────────────────────────────────────────────────
    WorkflowGroup(
        name="gpu",
        marker="gpu",
        description="GPU-accelerated tests requiring CUDA (cuDF, CuPy)",
        paths=[],  # Marked explicitly with @pytest.mark.gpu per test
        default_env="test-gpu",
        excluded_by_default=True,
    ),
]


# =====================================================================
# Pixi command definitions — derived from groups + composite commands
# =====================================================================

@dataclass
class PixiCommand:
    name: str
    description: str
    cmd: str  # The actual command (without 'pixi run')
    depends_on: list[str] = field(default_factory=list)
    feature: str = "test-unit-task"  # Which pixi feature defines this task
    category: Literal["core", "plotting", "special", "composite", "docs", "lint", "build"] = "core"


def get_pixi_commands() -> list[PixiCommand]:
    """Return the list of expected pixi commands derived from groups + composites."""
    cmds: list[PixiCommand] = []

    # Per-group commands (derived from GROUPS)
    for g in GROUPS:
        if not g.paths:
            continue  # GPU etc. are marked per-test, not per-file
        task_name = g.pixi_task_override or f"test-{g.name.replace('_', '-')}"
        cmds.append(PixiCommand(
            name=task_name,
            description=g.description,
            cmd=f"pytest holoviews/tests -m {g.marker} -n logical --dist loadgroup",
            category="core" if g.name in ("core", "operation") else
                     "plotting" if g.name.startswith("plotting") else
                     "special",
        ))

    # Composite commands
    cmds += [
        PixiCommand(
            name="test-unit",
            description="Full unit test suite (all groups except ui/gpu)",
            cmd="pytest holoviews/tests -n logical --dist loadgroup",
            category="composite",
        ),
        PixiCommand(
            name="check",
            description="Local quick check: lint + type + core unit tests",
            cmd="",
            depends_on=["lint", "type-ty", "test-unit-core"],
            category="composite",
        ),
        PixiCommand(
            name="test-all",
            description="Full regression: unit + example notebooks",
            cmd="",
            depends_on=["test-unit", "test-example"],
            category="composite",
        ),
        PixiCommand(
            name="test-release",
            description="Pre-release check: lint + type + all tests",
            cmd="",
            depends_on=["lint", "type-ty", "test-all"],
            category="composite",
        ),
    ]

    # Docs commands
    cmds += [
        PixiCommand(
            name="docs-build",
            description="Full documentation build with gallery",
            cmd="",
            depends_on=["_docs-generate-rst", "_docs-refmanual", "_docs-generate"],
            feature="doc",
            category="docs",
        ),
        PixiCommand(
            name="docs-build-quick",
            description="Quick documentation build (no gallery)",
            cmd="",
            depends_on=["_docs-generate-rst", "_docs-refmanual", "_docs-generate-quick"],
            feature="doc",
            category="docs",
        ),
    ]

    # Lint / type
    cmds += [
        PixiCommand(
            name="lint",
            description="Run pre-commit linting on all files",
            cmd="pre-commit run --all-files",
            feature="lint",
            category="lint",
        ),
        PixiCommand(
            name="type-ty",
            description="Type checking with ty",
            cmd="ty check .",
            feature="type-task",
            category="lint",
        ),
    ]

    return cmds


# =====================================================================
# Helpers
# =====================================================================

def get_all_markers() -> list[str]:
    """Return all marker names defined in the map."""
    markers = set()
    for g in GROUPS:
        markers.add(g.marker)
        markers.update(g.also_markers)
    return sorted(markers)


def get_excluded_by_default_markers() -> list[str]:
    """Return markers that should be excluded by default (ui, gpu)."""
    return [g.marker for g in GROUPS if g.excluded_by_default]


def file_matches_group(rel_path: str, group: WorkflowGroup) -> bool:
    """Check if a test file path (relative to tests/) belongs to a group."""
    return any(p in rel_path for p in group.paths)


def get_markers_for_file(rel_path: str) -> list[str]:
    """Return all markers that should apply to a given test file path."""
    markers: list[str] = []
    for g in GROUPS:
        if file_matches_group(rel_path, g):
            if g.marker not in markers:
                markers.append(g.marker)
            for m in g.also_markers:
                if m not in markers:
                    markers.append(m)
    return markers


# =====================================================================
# Content generators — produce auto-generated blocks for derived files
# =====================================================================

def generate_pixi_test_tasks_block() -> str:
    """Generate the [feature.test-unit-task.tasks] block for pixi.toml.

    Returns just the task lines (without the section header),
    sorted by category then name.
    """
    cmds = [c for c in get_pixi_commands() if c.feature == "test-unit-task"]

    # Sort: core → plotting → special → composite
    cat_order = {"core": 0, "plotting": 1, "special": 2, "composite": 3}
    cmds.sort(key=lambda c: (cat_order.get(c.category, 99), c.name))

    lines: list[str] = []
    for cmd in cmds:
        if cmd.depends_on:
            deps = ", ".join(f'"{d}"' for d in cmd.depends_on)
            lines.append(f'{cmd.name} = {{ depends-on = [{deps}] }}')
        else:
            lines.append(f'{cmd.name} = \'{cmd.cmd}\'')
    return "\n".join(lines) + "\n"


def generate_ci_mapping_comment() -> str:
    """Generate the CI workflow ↔ local command mapping comment block.

    Returns a YAML comment block (lines starting with #) that documents
    the mapping between CI jobs and local pixi commands.
    """
    lines = [
        "CI workflow ↔ local pixi command mapping (auto-generated from scripts/workflow_map.py):",
        "",
    ]

    # Organize by logical group
    sections = [
        ("Local quick check", ["check"]),
        ("Core unit suite", ["test-unit-core"]),
        ("Plotting backends", ["test-plotting"]),
        ("IPython/display", ["test-ipython"]),
        ("Datashader path", ["test-datashader"]),
        ("Full regression", ["test-all"]),
        ("Pre-release check", ["test-release"]),
        ("Docs", ["docs-build-quick", "docs-build"]),
    ]

    cmd_map = {c.name: c for c in get_pixi_commands()}

    for label, cmd_names in sections:
        for i, cmd_name in enumerate(cmd_names):
            cmd = cmd_map.get(cmd_name)
            if not cmd:
                continue
            prefix = f"  {label:<20s}: " if i == 0 else " " * 24
            marker_info = ""
            # Extract marker from command if present
            if "-m " in cmd.cmd:
                import re
                m = re.search(r"-m (\w+)", cmd.cmd)
                if m:
                    marker_info = f" → -m {m.group(1)}"
            lines.append(f"{prefix}pixi run {cmd_name}{marker_info}")

    lines.append("")
    lines.append("All of the above ultimately resolve to pytest markers defined in")
    lines.append("workflow_map.py and applied dynamically by conftest.py.")

    # Prefix every line with "# "
    return "\n".join(f"# {line}" if line else "#" for line in lines) + "\n"


def generate_docs_mapping_table() -> str:
    """Generate the Command ↔ Marker ↔ Directory mapping table for docs.

    Returns a markdown table that documents the three-layer mapping.
    """
    header = (
        "| Pixi task              | pytest marker       | "
        "Directories / files                                                 |"
    )
    separator = (
        "|------------------------|---------------------|"
        "---------------------------------------------------------------------|"
    )

    rows: list[str] = []
    for g in GROUPS:
        if not g.paths and not g.also_markers and g.marker not in ("ui", "gpu"):
            continue
        task_name = g.pixi_task_override or f"test-{g.name.replace('_', '-')}"
        paths_str = ", ".join(g.paths[:3])
        if len(g.paths) > 3:
            paths_str += f", … ({len(g.paths)} total)"
        if not g.paths:
            paths_str = f"marked explicitly with `@pytest.mark.{g.marker}`"
        rows.append(f"| `{task_name:<20s}` | `{g.marker:<19s}` | {paths_str:<67s} |")

    return "\n".join([header, separator] + rows) + "\n"

