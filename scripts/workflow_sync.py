#!/usr/bin/env python3
"""
Synchronize and verify consistency of HoloViews developer workflow across
all layers (pytest markers, pixi tasks, CI jobs, documentation).

Single Source of Truth: scripts/workflow_map.py

This script ensures that derived artifacts (conftest fallback list,
pixi.toml task names, developer docs mapping table) stay in sync with
the workflow map.

Usage:
    python scripts/workflow_sync.py check     # Verify consistency (CI, pre-commit)
    python scripts/workflow_sync.py sync      # Auto-update derived artifacts
    python scripts/workflow_sync.py status    # Show current state
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
TESTS_DIR = PROJECT_ROOT / "holoviews" / "tests"

sys.path.insert(0, str(SCRIPT_DIR))
from workflow_map import (  # noqa: E402
    GROUPS,
    WorkflowGroup,
    file_matches_group,
    get_all_markers,
    get_excluded_by_default_markers,
    get_markers_for_file,
    get_pixi_commands,
)


# =====================================================================
# Checker: each derived artifact is checked against the SSOT
# =====================================================================

@dataclass
class CheckResult:
    name: str
    status: Literal["ok", "warn", "fail"]
    details: list[str]

    def __bool__(self):
        return self.status != "fail"


def _mark(text: str, status: Literal["ok", "warn", "fail"]) -> str:
    symbols = {"ok": "✓", "warn": "⚠", "fail": "✗"}
    return f"{symbols[status]} {text}"


def check_conftest_fallback() -> CheckResult:
    """Verify conftest.py fallback marker list matches workflow_map."""
    conftest_path = PROJECT_ROOT / "holoviews" / "tests" / "conftest.py"
    content = conftest_path.read_text()

    details = []
    expected_markers = get_all_markers()
    expected_excluded = get_excluded_by_default_markers()

    # Extract fallback _MARKERS tuple
    m = re.search(r"_MARKERS = \((.*?)\)", content, re.DOTALL)
    if not m:
        return CheckResult("conftest fallback markers", "fail", ["Cannot find _MARKERS tuple"])

    fallback_markers = sorted(re.findall(r'"([a-z_]+)"', m.group(1)))
    if fallback_markers != sorted(expected_markers):
        details.append(f"Fallback markers mismatch: {set(fallback_markers) ^ set(expected_markers)}")
        return CheckResult("conftest fallback markers", "fail", details)

    # Extract fallback _EXCLUDED_BY_DEFAULT
    m2 = re.search(r"_EXCLUDED_BY_DEFAULT = \((.*?)\)", content, re.DOTALL)
    if not m2:
        return CheckResult("conftest fallback excluded", "warn", ["Cannot find _EXCLUDED_BY_DEFAULT"])

    fallback_excluded = sorted(re.findall(r'"([a-z_]+)"', m2.group(1)))
    if fallback_excluded != sorted(expected_excluded):
        details.append(f"Excluded list mismatch: {set(fallback_excluded) ^ set(expected_excluded)}")
        return CheckResult("conftest fallback excluded", "fail", details)

    details.append(f"All {len(expected_markers)} markers and {len(expected_excluded)} excluded in sync")
    return CheckResult("conftest fallback markers", "ok", details)


def check_pixi_tasks() -> CheckResult:
    """Verify pixi.toml has tasks for every group marker (except ui/gpu special ones)."""
    pixi_path = PROJECT_ROOT / "pixi.toml"
    with open(pixi_path, "rb") as f:
        pixi = tomllib.load(f)

    details = []
    expected_cmds = get_pixi_commands()

    # Collect all task names across features
    all_tasks: set[str] = set()
    for feat_name, feat in pixi.get("feature", {}).items():
        tasks = feat.get("tasks", {})
        all_tasks.update(tasks.keys())

    # Also check default tasks
    all_tasks.update(pixi.get("tasks", {}).keys())

    missing = []
    for cmd in expected_cmds:
        if cmd.name not in all_tasks:
            missing.append(cmd.name)

    if missing:
        details.append(f"Missing pixi tasks: {missing}")
        return CheckResult("pixi tasks vs workflow map", "fail", details)

    details.append(f"All {len(expected_cmds)} expected commands present in pixi.toml")
    return CheckResult("pixi tasks vs workflow map", "ok", details)


def check_file_pytestmarks() -> CheckResult:
    """Check that pytestmark declarations in test files match the workflow map.

    Note: Hard-coded pytestmark in files is optional (conftest dynamically
    applies markers anyway). This check flags drift so you can decide whether
    to update them or remove them.
    Only custom markers (from workflow_map) are compared; built-in markers
    like xfail, skipif, parametrize are ignored.
    """
    details = []
    drifted = 0
    total_with_custom_markers = 0
    custom_markers_set = set(get_all_markers())

    for pyfile in sorted(TESTS_DIR.rglob("test_*.py")):
        rel = str(pyfile.relative_to(TESTS_DIR))
        content = pyfile.read_text()

        if "pytestmark" not in content:
            continue

        expected_markers = get_markers_for_file(rel)

        # Extract file-level pytestmark (module-level assignment),
        # NOT function-level decorators like @pytest.mark.gpu
        pytestmark_match = re.search(r"^pytestmark\s*=\s*(.+)$", content, re.MULTILINE)
        if not pytestmark_match:
            continue  # No file-level pytestmark, skip

        all_marker_names = re.findall(r"pytest\.mark\.([a-z_]+)", pytestmark_match.group(1))
        actual_custom = sorted(m for m in all_marker_names if m in custom_markers_set)

        if not actual_custom:
            continue  # pytestmark uses only built-in markers, skip

        total_with_custom_markers += 1

        if sorted(actual_custom) != sorted(expected_markers):
            drifted += 1
            if drifted <= 5:  # Only show first 5
                details.append(
                    f"  {rel}: expected {expected_markers}, got {actual_custom}"
                )

    if drifted > 5:
        details.append(f"  ... and {drifted - 5} more files")

    if drifted > 0:
        details.insert(0, f"{drifted}/{total_with_custom_markers} files with pytestmark drift")
        return CheckResult("file-level pytestmark consistency", "warn", details)

    details.append(f"All {total_with_custom_markers} files with custom pytestmark match workflow map")
    return CheckResult("file-level pytestmark consistency", "ok", details)


def check_docs_mapping() -> CheckResult:
    """Verify developer docs mapping table mentions all groups."""
    doc_path = PROJECT_ROOT / "doc" / "developer_guide" / "index.md"
    content = doc_path.read_text()

    details = []
    expected_groups = [g for g in GROUPS if g.paths]  # Groups with files

    missing = []
    for g in expected_groups:
        if g.marker not in content:
            missing.append(g.marker)

    if missing:
        details.append(f"Markers not mentioned in docs: {missing}")
        return CheckResult("developer docs mapping", "warn", details)

    details.append(f"All {len(expected_groups)} group markers referenced in docs")
    return CheckResult("developer docs mapping", "ok", details)


def check_pyproject_markers() -> CheckResult:
    """Verify pyproject.toml pytest markers match the map."""
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)

    details = []
    markers_cfg = pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
    cfg_markers = [m.split(":")[0].strip() for m in markers_cfg if ":" in m]

    expected = get_all_markers()

    missing = set(expected) - set(cfg_markers)
    extra = set(cfg_markers) - set(expected)

    if missing or extra:
        if missing:
            details.append(f"Missing markers in pyproject.toml: {sorted(missing)}")
        if extra:
            details.append(f"Extra markers in pyproject.toml: {sorted(extra)}")
        return CheckResult("pyproject.toml markers", "fail", details)

    details.append(f"All {len(expected)} markers registered in pyproject.toml")
    return CheckResult("pyproject.toml markers", "ok", details)


# =====================================================================
# Syncer: update derived artifacts to match SSOT
# =====================================================================

def sync_conftest_fallback() -> bool:
    """Update the fallback marker list in conftest.py."""
    conftest_path = PROJECT_ROOT / "holoviews" / "tests" / "conftest.py"
    content = conftest_path.read_text()

    markers = get_all_markers()
    excluded = get_excluded_by_default_markers()

    markers_str = "(\n" + "".join(f'    "{m}",\n' for m in markers) + ")"
    excluded_str = "(" + ", ".join(f'"{m}"' for m in excluded) + ")"

    new_content = re.sub(
        r"_MARKERS = \(.*?\)",
        "_MARKERS = " + markers_str,
        content,
        count=1,
        flags=re.DOTALL,
    )
    new_content = re.sub(
        r"_EXCLUDED_BY_DEFAULT = \(.*?\)",
        "_EXCLUDED_BY_DEFAULT = " + excluded_str,
        new_content,
        count=1,
        flags=re.DOTALL,
    )

    if new_content != content:
        conftest_path.write_text(new_content)
        return True
    return False


def sync_file_pytestmarks() -> int:
    """Write pytestmark declarations to all test files that match a group.

    Returns number of files modified.
    """
    modified = 0

    for pyfile in sorted(TESTS_DIR.rglob("test_*.py")):
        rel = str(pyfile.relative_to(TESTS_DIR))
        expected_markers = get_markers_for_file(rel)

        if not expected_markers:
            continue

        content = pyfile.read_text()

        # Build desired pytestmark line
        marker_strs = [f"pytest.mark.{m}" for m in expected_markers]
        if len(marker_strs) == 1:
            marker_line = f"pytestmark = {marker_strs[0]}"
        else:
            marker_line = f"pytestmark = [{', '.join(marker_strs)}]"

        # Check if already correct
        if f"pytestmark = " in content:
            # Extract existing line
            match = re.search(r"^pytestmark = .+$", content, re.MULTILINE)
            if match and match.group(0).strip() == marker_line.strip():
                continue
            # Replace existing
            content = re.sub(r"^pytestmark = .+$", marker_line, content, count=1, flags=re.MULTILINE)
        else:
            # Insert after 'from __future__ import annotations'
            match = re.search(r"^from __future__ import annotations\s*$", content, re.MULTILINE)
            if not match:
                continue  # Skip files without future annotations
            insert_pos = match.end()
            content = content[:insert_pos] + "\n\n" + marker_line + "\n" + content[insert_pos:]

        pyfile.write_text(content)
        modified += 1

    return modified


def sync_pyproject_markers() -> bool:
    """Update pyproject.toml [tool.pytest.ini_options] markers list."""
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    content = pyproject_path.read_text()

    markers = []
    for g in GROUPS:
        markers.append(f'{g.marker}: {g.description}')
        for also in g.also_markers:
            # Avoid duplicates — only add description from main group
            pass

    # Build markers list in format:
    # markers = [
    #     "core: ...",
    #     "plotting_bokeh: ...",
    # ]

    # Use a dict to dedupe (last one wins for description)
    marker_dict: dict[str, str] = {}
    for g in GROUPS:
        marker_dict[g.marker] = g.description
        for also in g.also_markers:
            # also-markers inherit the parent's description or get a generic one
            if also not in marker_dict:
                marker_dict[also] = f"{also} test marker"

    # All unique markers sorted
    all_markers = get_all_markers()
    marker_lines = []
    for m in all_markers:
        desc = marker_dict.get(m, f"{m} test marker")
        marker_lines.append(f'    "{m}: {desc}",')

    markers_block = "markers = [\n" + "\n".join(marker_lines) + "\n]"

    # Replace existing markers block
    new_content = re.sub(
        r"markers = \[.*?\]",
        markers_block,
        content,
        count=1,
        flags=re.DOTALL,
    )

    if new_content != content:
        pyproject_path.write_text(new_content)
        return True
    return False


# =====================================================================
# CLI
# =====================================================================

ALL_CHECKS = [
    check_conftest_fallback,
    check_pyproject_markers,
    check_pixi_tasks,
    check_file_pytestmarks,
    check_docs_mapping,
]


def cmd_status() -> int:
    print("HoloViews Developer Workflow — Status")
    print("=" * 60)
    print(f"Single source of truth: scripts/workflow_map.py")
    print(f"Groups defined: {len(GROUPS)}")
    print(f"Markers: {', '.join(get_all_markers())}")
    print(f"Excluded by default: {', '.join(get_excluded_by_default_markers())}")
    print()

    # Show groups
    print("Groups:")
    for g in GROUPS:
        paths_str = ", ".join(g.paths[:3])
        if len(g.paths) > 3:
            paths_str += f", ... ({len(g.paths)} total)"
        also = f" (+also: {', '.join(g.also_markers)})" if g.also_markers else ""
        excl = " [excluded by default]" if g.excluded_by_default else ""
        print(f"  {g.name:20s} → {g.marker}{also}{excl}")
        if paths_str:
            print(f"    paths: {paths_str}")
    print()

    # Run checks
    print("Consistency checks:")
    all_ok = True
    for check_fn in ALL_CHECKS:
        result = check_fn()
        print(_mark(result.name, result.status))
        for d in result.details:
            print(f"    {d}")
        if not result:
            all_ok = False

    print()
    if all_ok:
        print("✓ All checks passed.")
        return 0
    else:
        print("Run `python scripts/workflow_sync.py sync` to auto-fix issues.")
        return 1


def cmd_check() -> int:
    """Run all checks; return non-zero if any fail."""
    failures = 0
    warnings = 0

    for check_fn in ALL_CHECKS:
        result = check_fn()
        if result.status == "fail":
            failures += 1
            print(_mark(result.name, "fail"))
            for d in result.details:
                print(f"    {d}")
        elif result.status == "warn":
            warnings += 1
            print(_mark(result.name, "warn"))
            for d in result.details:
                print(f"    {d}")
        else:
            print(_mark(result.name, "ok"))

    print()
    if failures == 0 and warnings == 0:
        print(f"All {len(ALL_CHECKS)} checks passed.")
        return 0
    elif failures == 0:
        print(f"{warnings} warning(s), 0 failures.")
        return 0  # Warnings don't fail CI
    else:
        print(f"{failures} failure(s), {warnings} warning(s).")
        print("Run `python scripts/workflow_sync.py sync` to auto-fix.")
        return 1


def cmd_sync() -> int:
    """Sync all derived artifacts to match the workflow map."""
    changes = []

    if sync_conftest_fallback():
        changes.append("conftest.py fallback markers updated")
    else:
        print("✓ conftest.py fallback markers already in sync")

    if sync_pyproject_markers():
        changes.append("pyproject.toml markers updated")
    else:
        print("✓ pyproject.toml markers already in sync")

    n = sync_file_pytestmarks()
    if n > 0:
        changes.append(f"{n} test files updated with pytestmark")
    else:
        print("✓ file-level pytestmarks already in sync")

    print()
    if changes:
        print("Changes made:")
        for c in changes:
            print(f"  - {c}")
        print()
        print("Note: pixi.toml tasks and docs mapping table are NOT auto-updated.")
        print("Update them manually after changing the workflow map.")
        return 0
    else:
        print("Nothing to sync — everything is already consistent.")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Synchronize HoloViews developer workflow layers.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show workflow map state and run all checks")
    sub.add_parser("check", help="Verify all derived artifacts are in sync (for CI/pre-commit)")
    sub.add_parser("sync", help="Auto-update derived artifacts to match the workflow map")

    args = parser.parse_args()

    if args.command == "status":
        sys.exit(cmd_status())
    elif args.command == "check":
        sys.exit(cmd_check())
    elif args.command == "sync":
        sys.exit(cmd_sync())


if __name__ == "__main__":
    main()
