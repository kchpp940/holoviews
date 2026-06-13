from __future__ import annotations

import enum
import json
import os
import shutil
import sys
import typing as t
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except Exception:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]

from .dependencies import _is_installed, _no_import_version

if t.TYPE_CHECKING:
    from types import ModuleType


class CapabilityStatus(enum.Enum):
    AVAILABLE = "available"
    NOT_INSTALLED = "not_installed"
    VERSION_TOO_OLD = "version_too_old"
    IMPORT_ERROR = "import_error"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class CapabilityType(enum.Enum):
    BACKEND = "backend"
    DATASHADER = "datashader"
    NOTEBOOK = "notebook"
    STATIC_EXPORT = "static_export"
    DATA_LIBRARY = "data_library"
    EXTRA = "extra"
    CI_GROUP = "ci_group"
    MISC = "misc"


@dataclass(frozen=True)
class CapabilityDiagnostic:
    name: str
    type: CapabilityType
    status: CapabilityStatus
    version: str | None = None
    min_version: str | None = None
    package_name: str | None = None
    import_name: str | None = None
    error_message: str | None = None
    fix_suggestions: tuple[str, ...] = ()
    details: dict[str, t.Any] = field(default_factory=dict, hash=False)

    @property
    def available(self) -> bool:
        return self.status == CapabilityStatus.AVAILABLE

    def __bool__(self) -> bool:
        return self.available

    def __str__(self) -> str:
        lines = [f"Capability: {self.name} ({self.type.value})"]
        lines.append(f"  Status: {self.status.value}")
        if self.version:
            lines.append(f"  Version: {self.version}")
        if self.min_version:
            lines.append(f"  Minimum required: {self.min_version}")
        if self.error_message:
            lines.append(f"  Error: {self.error_message}")
        if self.fix_suggestions:
            lines.append("  Suggestions:")
            for suggestion in self.fix_suggestions:
                lines.append(f"    - {suggestion}")
        return "\n".join(lines)

    def format_skip_reason(self) -> str:
        parts = [f"{self.name} {self.status.value}"]
        if self.error_message:
            parts.append(self.error_message)
        if self.fix_suggestions:
            parts.append("Fix: " + "; ".join(self.fix_suggestions))
        return " | ".join(parts)

    def with_error(
        self,
        status: CapabilityStatus,
        error_message: str,
        fix_suggestions: tuple[str, ...] | None = None,
    ) -> CapabilityDiagnostic:
        return CapabilityDiagnostic(
            name=self.name,
            type=self.type,
            status=status,
            version=self.version,
            min_version=self.min_version,
            package_name=self.package_name,
            import_name=self.import_name,
            error_message=error_message,
            fix_suggestions=fix_suggestions if fix_suggestions is not None else self.fix_suggestions,
            details=self.details,
        )


class CapabilityError(Exception):
    def __init__(self, diagnostic: CapabilityDiagnostic):
        self.diagnostic = diagnostic
        super().__init__(str(diagnostic))


_BACKEND_MIN_VERSIONS: dict[str, tuple[int, ...]] = {
    "bokeh": (3, 0, 0),
    "matplotlib": (3, 5, 0),
    "plotly": (5, 0, 0),
}

_BACKEND_PACKAGE_MAP: dict[str, str] = {
    "bokeh": "bokeh",
    "matplotlib": "matplotlib",
    "plotly": "plotly",
}

_BACKEND_IMPORT_MAP: dict[str, str] = {
    "bokeh": "holoviews.plotting.bokeh",
    "matplotlib": "holoviews.plotting.mpl",
    "plotly": "holoviews.plotting.plotly",
}

_DATASHADER_MIN_VERSION: tuple[int, ...] = (0, 14, 0)

_NOTEBOOK_PACKAGES = [
    ("IPython", "IPython"),
    ("jupyter_bokeh", "jupyter_bokeh"),
    ("ipywidgets_bokeh", "ipywidgets_bokeh"),
    ("jupyterlab", "jupyterlab"),
    ("notebook", "notebook"),
]

_STATIC_EXPORT_DEPS: dict[str, dict[str, dict[str, t.Any]]] = {
    "png": {
        "bokeh": {"packages": ["selenium"], "requires_webdriver": True},
        "matplotlib": {"packages": []},
        "plotly": {"packages": ["kaleido"]},
    },
    "svg": {
        "bokeh": {"packages": ["selenium"], "requires_webdriver": True},
        "matplotlib": {"packages": []},
        "plotly": {"packages": ["kaleido"]},
    },
    "pdf": {
        "bokeh": {"packages": ["selenium"], "requires_webdriver": True},
        "matplotlib": {"packages": []},
        "plotly": {"packages": ["kaleido"]},
    },
    "html": {
        "bokeh": {"packages": []},
        "matplotlib": {"packages": []},
        "plotly": {"packages": []},
    },
    "gif": {
        "bokeh": {"packages": ["selenium", "pillow"], "requires_webdriver": True},
        "matplotlib": {"packages": ["pillow"]},
        "plotly": {"packages": ["kaleido", "pillow"]},
    },
    "mp4": {
        "bokeh": {"packages": ["selenium"], "requires_webdriver": True, "requires_binary": "ffmpeg"},
        "matplotlib": {"packages": [], "requires_binary": "ffmpeg"},
        "plotly": {"packages": ["kaleido"], "requires_binary": "ffmpeg"},
    },
    "webm": {
        "bokeh": {"packages": ["selenium"], "requires_webdriver": True, "requires_binary": "ffmpeg"},
        "matplotlib": {"packages": [], "requires_binary": "ffmpeg"},
        "plotly": {"packages": ["kaleido"], "requires_binary": "ffmpeg"},
    },
}


_HV_ROOT = Path(__file__).resolve().parents[3]


def _load_toml(path: Path) -> dict[str, t.Any] | None:
    if tomllib is None or not path.exists():
        return None
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except Exception:
        return None


def _extract_package_name(dep_spec: str) -> str:
    for sep in [" ", ">=", "<=", "==", "!=", "~=", ">", "<", ";", "["]:
        if sep in dep_spec:
            dep_spec = dep_spec.split(sep)[0]
    return dep_spec.strip().lower().replace("-", "_").replace(".", "_")


def _load_pyproject_extras() -> dict[str, list[str]]:
    pyproject = _load_toml(_HV_ROOT / "pyproject.toml")
    if pyproject is None:
        return {"recommended": ["matplotlib", "plotly"]}
    extras_raw = pyproject.get("project", {}).get("optional-dependencies", {})
    result: dict[str, list[str]] = {}
    for name, deps in extras_raw.items():
        result[name] = [_extract_package_name(d) for d in deps]
    return result


_PYPROJECT_EXTRAS: dict[str, list[str]] = _load_pyproject_extras()


def _load_pixi_feature_groups() -> dict[str, list[str]]:
    pixi = _load_toml(_HV_ROOT / "pixi.toml")
    if pixi is None:
        return {
            "required": ["bokeh", "panel", "param", "numpy", "pandas"],
            "optional": [
                "datashader", "matplotlib", "plotly", "xarray", "dask",
                "cftime", "networkx", "polars", "scipy", "shapely", "pillow",
                "selenium", "ffmpeg",
            ],
            "test-core": ["pytest"],
            "test-ui": ["playwright"],
            "test-gpu": ["cudf", "cupy"],
        }
    result: dict[str, list[str]] = {}
    for feature_name, feature_body in pixi.get("feature", {}).items():
        deps = feature_body.get("dependencies", {}) if isinstance(feature_body, dict) else {}
        pkg_names = [
            _extract_package_name(str(k)) for k in deps.keys()
        ] if isinstance(deps, dict) else []
        if pkg_names:
            result[feature_name] = pkg_names
    return result


_PIXI_FEATURE_GROUPS: dict[str, list[str]] = _load_pixi_feature_groups()


def _load_pixi_environments() -> dict[str, list[str]]:
    pixi = _load_toml(_HV_ROOT / "pixi.toml")
    if pixi is None:
        return {
            "core": ["test-core"],
            "unit": ["test-310", "test-311", "test-312", "test-313", "test-314"],
            "ui": ["test-ui"],
            "type": ["type"],
        }
    env_configs = pixi.get("environments", {})
    result: dict[str, list[str]] = {"core": [], "unit": [], "ui": [], "type": [], "gpu": []}
    for env_name in env_configs:
        if env_name == "test-core":
            result["core"].append(env_name)
        elif env_name.startswith("test-3"):
            result["unit"].append(env_name)
        elif env_name == "test-ui":
            result["ui"].append(env_name)
        elif env_name == "test-gpu":
            result["gpu"].append(env_name)
        elif env_name == "type":
            result["type"].append(env_name)
    return {k: sorted(v) for k, v in result.items() if v}


def _load_ci_groups() -> dict[str, dict[str, t.Any]]:
    envs_map = _load_pixi_environments()
    defaults: dict[str, dict[str, t.Any]] = {
        "core": {"backends": ["bokeh"], "optional": False, "description": "Core tests with minimal dependencies (bokeh only)"},
        "unit": {"backends": ["bokeh", "matplotlib", "plotly"], "optional": True, "description": "Full unit tests with all backends and optional deps"},
        "ui": {"backends": ["bokeh"], "optional": True, "description": "Browser UI tests (requires playwright)"},
        "type": {"backends": [], "optional": False, "description": "Static type checking"},
        "gpu": {"backends": ["bokeh"], "optional": True, "description": "GPU accelerated tests (requires cudf/cupy)"},
    }
    result: dict[str, dict[str, t.Any]] = {}
    for suite, info in defaults.items():
        if suite in envs_map:
            result[suite] = {
                "environments": envs_map[suite],
                "backends": info["backends"],
                "optional": info["optional"],
                "description": info["description"],
            }
    return result


_CI_GROUPS: dict[str, dict[str, t.Any]] = _load_ci_groups()


def _version_tuple_to_str(version_tuple: tuple[int, ...]) -> str:
    return ".".join(map(str, version_tuple))


def _check_version(
    package_name: str, min_version: tuple[int, ...] | None
) -> tuple[CapabilityStatus, str | None]:
    if not _is_installed(package_name):
        return CapabilityStatus.NOT_INSTALLED, None

    version_tuple = _no_import_version(package_name)
    version_str = _version_tuple_to_str(version_tuple)

    if min_version and version_tuple < min_version:
        return CapabilityStatus.VERSION_TOO_OLD, version_str

    return CapabilityStatus.AVAILABLE, version_str


def _check_binary(binary_name: str) -> bool:
    return shutil.which(binary_name) is not None


def _build_fix_suggestions(
    package_name: str, backend_name: str | None, min_version_str: str | None
) -> tuple[str, ...]:
    suggestions: list[str] = []
    suggestions.append(f"Install {package_name}: pip install {package_name}")
    if backend_name:
        suggestions.append(
            f"Install with HoloViews extras: pip install holoviews[{backend_name}]"
        )
    if min_version_str:
        suggestions.append(
            f"Upgrade {package_name}: pip install --upgrade {package_name}>={min_version_str}"
        )
    return tuple(suggestions)


def _try_import_package(import_name: str, package_name: str) -> CapabilityDiagnostic | None:
    try:
        __import__(import_name)
        return None
    except Exception as e:
        return CapabilityDiagnostic(
            name="",
            type=CapabilityType.MISC,
            status=CapabilityStatus.IMPORT_ERROR,
            error_message=f"Failed to import {import_name}: {type(e).__name__}: {e}",
            package_name=package_name,
            import_name=import_name,
            fix_suggestions=(
                f"Check that {package_name} is properly installed.",
                "Try reinstalling: pip install --force-reinstall " + package_name,
                "Check for conflicting versions of dependencies.",
            ),
        )


def _diagnose_backend(backend_name: str) -> CapabilityDiagnostic:
    package_name = _BACKEND_PACKAGE_MAP.get(backend_name, backend_name)
    import_name = _BACKEND_IMPORT_MAP.get(backend_name, backend_name)
    min_version = _BACKEND_MIN_VERSIONS.get(backend_name)
    min_version_str = _version_tuple_to_str(min_version) if min_version else None

    status, version = _check_version(package_name, min_version)

    fix_suggestions: tuple[str, ...] = ()
    error_message: str | None = None

    if status == CapabilityStatus.NOT_INSTALLED:
        fix_suggestions = _build_fix_suggestions(package_name, backend_name, None)
        error_message = f"{package_name} is not installed."
    elif status == CapabilityStatus.VERSION_TOO_OLD:
        fix_suggestions = _build_fix_suggestions(package_name, backend_name, min_version_str)
        error_message = (
            f"{package_name} version {version} is too old. "
            f"Required: {min_version_str} or higher."
        )
    elif status == CapabilityStatus.AVAILABLE:
        import_error = _try_import_package(import_name, package_name)
        if import_error is not None:
            status = CapabilityStatus.IMPORT_ERROR
            error_message = import_error.error_message
            fix_suggestions = import_error.fix_suggestions

    return CapabilityDiagnostic(
        name=backend_name,
        type=CapabilityType.BACKEND,
        status=status,
        version=version,
        min_version=min_version_str,
        package_name=package_name,
        import_name=import_name,
        error_message=error_message,
        fix_suggestions=fix_suggestions,
        details={"plotting_module": import_name},
    )


def _diagnose_datashader() -> CapabilityDiagnostic:
    min_version_str = _version_tuple_to_str(_DATASHADER_MIN_VERSION)
    status, version = _check_version("datashader", _DATASHADER_MIN_VERSION)

    fix_suggestions: tuple[str, ...] = ()
    error_message: str | None = None

    if status == CapabilityStatus.NOT_INSTALLED:
        fix_suggestions = _build_fix_suggestions("datashader", None, None)
        error_message = "datashader is not installed."
    elif status == CapabilityStatus.VERSION_TOO_OLD:
        fix_suggestions = _build_fix_suggestions("datashader", None, min_version_str)
        error_message = (
            f"datashader version {version} is too old. "
            f"Required: {min_version_str} or higher."
        )
    elif status == CapabilityStatus.AVAILABLE:
        import_error = _try_import_package("datashader", "datashader")
        if import_error is not None:
            status = CapabilityStatus.IMPORT_ERROR
            error_message = import_error.error_message
            fix_suggestions = import_error.fix_suggestions

    details = {
        "supports_aggregate": status == CapabilityStatus.AVAILABLE,
        "supports_transfer_functions": status == CapabilityStatus.AVAILABLE,
    }

    return CapabilityDiagnostic(
        name="datashader",
        type=CapabilityType.DATASHADER,
        status=status,
        version=version,
        min_version=min_version_str,
        package_name="datashader",
        import_name="datashader",
        error_message=error_message,
        fix_suggestions=fix_suggestions,
        details=details,
    )


def _diagnose_notebook() -> dict[str, CapabilityDiagnostic]:
    results: dict[str, CapabilityDiagnostic] = {}

    for name, package_name in _NOTEBOOK_PACKAGES:
        status, version = _check_version(package_name, None)

        fix_suggestions: tuple[str, ...] = ()
        error_message: str | None = None

        if status == CapabilityStatus.NOT_INSTALLED:
            fix_suggestions = (f"Install {package_name}: pip install {package_name}",)
            error_message = f"{package_name} is not installed."

        results[name] = CapabilityDiagnostic(
            name=name,
            type=CapabilityType.NOTEBOOK,
            status=status,
            version=version,
            package_name=package_name,
            import_name=name,
            error_message=error_message,
            fix_suggestions=fix_suggestions,
        )

    return results


def _diagnose_static_export_for_backend(
    fmt: str, backend: str
) -> tuple[CapabilityStatus, str | None, tuple[str, ...], dict[str, t.Any]]:
    backend_diag = get_backend_capability(backend)
    if not backend_diag.available:
        return (
            CapabilityStatus.NOT_INSTALLED,
            f"Backend {backend} is not available: {backend_diag.error_message}",
            backend_diag.fix_suggestions,
            {"backend": backend, "backend_available": False},
        )

    deps_info = _STATIC_EXPORT_DEPS.get(fmt, {}).get(backend, {})
    packages = deps_info.get("packages", [])
    requires_binary = deps_info.get("requires_binary")
    requires_webdriver = deps_info.get("requires_webdriver", False)

    errors: list[str] = []
    all_suggestions: list[str] = []

    for pkg in packages:
        pkg_status, _ = _check_version(pkg, None)
        if pkg_status != CapabilityStatus.AVAILABLE:
            errors.append(f"{pkg} is not installed")
            all_suggestions.append(f"Install {pkg}: pip install {pkg}")

    if requires_binary and not _check_binary(requires_binary):
        errors.append(f"Required binary '{requires_binary}' not found in PATH")
        all_suggestions.append(
            f"Install {requires_binary}: see https://holoviews.org/user_guide/Exporting_and_Archiving.html"
        )

    if requires_webdriver:
        for driver in ["geckodriver", "chromedriver"]:
            if _check_binary(driver):
                break
        else:
            errors.append("No webdriver (geckodriver/chromedriver) found in PATH")
            all_suggestions.append(
                "Install a webdriver: 'conda install -c conda-forge firefox geckodriver' or 'brew install chromedriver'"
            )

    if errors:
        return (
            CapabilityStatus.NOT_INSTALLED,
            "; ".join(errors),
            tuple(all_suggestions),
            {
                "backend": backend,
                "backend_available": True,
                "missing_packages": [p for p in packages if _check_version(p, None)[0] != CapabilityStatus.AVAILABLE],
                "missing_binary": requires_binary if (requires_binary and not _check_binary(requires_binary)) else None,
                "missing_webdriver": requires_webdriver,
            },
        )

    return (
        CapabilityStatus.AVAILABLE,
        None,
        (),
        {
            "backend": backend,
            "backend_available": True,
            "packages": packages,
            "requires_binary": requires_binary,
            "requires_webdriver": requires_webdriver,
        },
    )


def _diagnose_static_export(backend: str | None = None) -> dict[str, CapabilityDiagnostic]:
    results: dict[str, CapabilityDiagnostic] = {}
    backends_to_check = [backend] if backend else list(_BACKEND_PACKAGE_MAP.keys())

    for fmt in _STATIC_EXPORT_DEPS:
        fmt_details: dict[str, t.Any] = {}
        available_backends: list[str] = []
        unavailable_backends: list[str] = []
        all_errors: list[str] = []
        all_suggestions: set[str] = set()

        for bk in backends_to_check:
            if bk not in _STATIC_EXPORT_DEPS.get(fmt, {}):
                continue

            status, err_msg, suggestions, details = _diagnose_static_export_for_backend(fmt, bk)
            fmt_details[bk] = details

            if status == CapabilityStatus.AVAILABLE:
                available_backends.append(bk)
            else:
                unavailable_backends.append(bk)
                if err_msg:
                    all_errors.append(f"[{bk}] {err_msg}")
                for s in suggestions:
                    all_suggestions.add(s)

        overall_status = (
            CapabilityStatus.AVAILABLE if available_backends else CapabilityStatus.NOT_INSTALLED
        )
        error_message = "; ".join(all_errors) if all_errors else None

        results[fmt] = CapabilityDiagnostic(
            name=f"static_export_{fmt}",
            type=CapabilityType.STATIC_EXPORT,
            status=overall_status,
            package_name=None,
            error_message=error_message,
            details={
                "format": fmt,
                "available_backends": available_backends,
                "unavailable_backends": unavailable_backends,
                "per_backend": fmt_details,
            },
            fix_suggestions=tuple(all_suggestions),
        )

    return results


def _diagnose_extras() -> dict[str, CapabilityDiagnostic]:
    results: dict[str, CapabilityDiagnostic] = {}

    for extra_name, packages in _PYPROJECT_EXTRAS.items():
        missing: list[str] = []
        installed: list[str] = []
        versions: dict[str, str] = {}

        for pkg in packages:
            status, version = _check_version(pkg, None)
            if status == CapabilityStatus.AVAILABLE:
                installed.append(pkg)
                if version:
                    versions[pkg] = version
            else:
                missing.append(pkg)

        status = CapabilityStatus.AVAILABLE if not missing else CapabilityStatus.NOT_INSTALLED
        error_message = (
            f"Missing packages: {', '.join(missing)}" if missing else None
        )
        fix_suggestions = (
            (f"Install all recommended extras: pip install holoviews[{extra_name}]",)
            if missing
            else ()
        )

        results[extra_name] = CapabilityDiagnostic(
            name=f"extra_{extra_name}",
            type=CapabilityType.EXTRA,
            status=status,
            package_name=None,
            error_message=error_message,
            fix_suggestions=fix_suggestions,
            details={
                "packages": packages,
                "installed": installed,
                "missing": missing,
                "versions": versions,
            },
        )

    for feature_name, packages in _PIXI_FEATURE_GROUPS.items():
        missing: list[str] = []
        installed: list[str] = []

        for pkg in packages:
            status, _ = _check_version(pkg, None)
            if status == CapabilityStatus.AVAILABLE:
                installed.append(pkg)
            else:
                missing.append(pkg)

        status = CapabilityStatus.AVAILABLE if not missing else CapabilityStatus.NOT_INSTALLED
        error_message = (
            f"Missing packages in pixi feature '{feature_name}': {', '.join(missing)}"
            if missing
            else None
        )

        results[f"pixi_{feature_name}"] = CapabilityDiagnostic(
            name=f"pixi_feature_{feature_name}",
            type=CapabilityType.EXTRA,
            status=status,
            package_name=None,
            error_message=error_message,
            fix_suggestions=(),
            details={
                "source": "pixi.toml",
                "packages": packages,
                "installed": installed,
                "missing": missing,
            },
        )

    return results


def _diagnose_ci_groups() -> dict[str, CapabilityDiagnostic]:
    results: dict[str, CapabilityDiagnostic] = {}

    for group_name, group_info in _CI_GROUPS.items():
        backends = group_info.get("backends", [])
        available_backends = [b for b in backends if is_backend_available(b)]
        missing_backends = [b for b in backends if not is_backend_available(b)]

        if missing_backends and not group_info.get("optional", False):
            status = CapabilityStatus.NOT_INSTALLED
            error_message = f"Required backends missing: {', '.join(missing_backends)}"
        elif missing_backends:
            status = CapabilityStatus.AVAILABLE
            error_message = None
        else:
            status = CapabilityStatus.AVAILABLE
            error_message = None

        fix_suggestions: tuple[str, ...] = ()
        if missing_backends:
            fix_suggestions = tuple(
                f"Install backend {b}: pip install {b}" for b in missing_backends
            )

        results[group_name] = CapabilityDiagnostic(
            name=f"ci_group_{group_name}",
            type=CapabilityType.CI_GROUP,
            status=status,
            package_name=None,
            error_message=error_message,
            fix_suggestions=fix_suggestions,
            details={
                "environments": group_info.get("environments", []),
                "required_backends": backends,
                "available_backends": available_backends,
                "missing_backends": missing_backends,
                "optional": group_info.get("optional", False),
                "description": group_info.get("description", ""),
            },
        )

    return results


@cache
def get_backend_capability(backend: str) -> CapabilityDiagnostic:
    if backend not in _BACKEND_PACKAGE_MAP:
        return CapabilityDiagnostic(
            name=backend,
            type=CapabilityType.BACKEND,
            status=CapabilityStatus.UNKNOWN,
            error_message=f"Unknown backend: {backend}",
            fix_suggestions=(
                f"Available backends: {', '.join(_BACKEND_PACKAGE_MAP.keys())}",
            ),
        )
    return _diagnose_backend(backend)


@cache
def get_datashader_capability() -> CapabilityDiagnostic:
    return _diagnose_datashader()


@cache
def get_notebook_capabilities() -> dict[str, CapabilityDiagnostic]:
    return _diagnose_notebook()


@cache
def get_static_export_capabilities(backend: str | None = None) -> dict[str, CapabilityDiagnostic]:
    return _diagnose_static_export(backend)


@cache
def get_extra_capabilities() -> dict[str, CapabilityDiagnostic]:
    return _diagnose_extras()


@cache
def get_ci_group_capabilities() -> dict[str, CapabilityDiagnostic]:
    return _diagnose_ci_groups()


def get_backend_static_export_capability(backend: str, fmt: str) -> CapabilityDiagnostic:
    if backend not in _BACKEND_PACKAGE_MAP:
        return get_backend_capability(backend)
    if fmt not in _STATIC_EXPORT_DEPS:
        backend_diag = get_backend_capability(backend)
        return CapabilityDiagnostic(
            name=f"static_export_{fmt}_{backend}",
            type=CapabilityType.STATIC_EXPORT,
            status=backend_diag.status,
            version=backend_diag.version,
            package_name=backend_diag.package_name,
            import_name=backend_diag.import_name,
            error_message=backend_diag.error_message,
            fix_suggestions=backend_diag.fix_suggestions,
            details={"format": fmt, "backend": backend, "tracked": False},
        )
    if backend not in _STATIC_EXPORT_DEPS.get(fmt, {}):
        return CapabilityDiagnostic(
            name=f"static_export_{fmt}_{backend}",
            type=CapabilityType.STATIC_EXPORT,
            status=CapabilityStatus.DISABLED,
            error_message=f"Backend {backend} does not support {fmt} export",
            fix_suggestions=(
                f"Try one of these backends: {', '.join(_STATIC_EXPORT_DEPS.get(fmt, {}).keys())}",
            ),
        )

    status, err_msg, suggestions, details = _diagnose_static_export_for_backend(fmt, backend)
    return CapabilityDiagnostic(
        name=f"static_export_{fmt}_{backend}",
        type=CapabilityType.STATIC_EXPORT,
        status=status,
        package_name=None,
        error_message=err_msg,
        fix_suggestions=suggestions,
        details=details,
    )


def get_all_capabilities() -> dict[str, CapabilityDiagnostic | dict[str, CapabilityDiagnostic]]:
    return {
        "backends": {bk: get_backend_capability(bk) for bk in _BACKEND_PACKAGE_MAP},
        "datashader": get_datashader_capability(),
        "notebook": get_notebook_capabilities(),
        "static_export": get_static_export_capabilities(),
        "extras": get_extra_capabilities(),
        "ci_groups": get_ci_group_capabilities(),
    }


def require_backend(backend: str) -> CapabilityDiagnostic:
    diag = get_backend_capability(backend)
    if not diag.available:
        raise CapabilityError(diag)
    return diag


def require_datashader() -> CapabilityDiagnostic:
    diag = get_datashader_capability()
    if not diag.available:
        raise CapabilityError(diag)
    return diag


def require_static_export(backend: str, fmt: str) -> CapabilityDiagnostic:
    diag = get_backend_static_export_capability(backend, fmt)
    if not diag.available:
        raise CapabilityError(diag)
    return diag


def import_backend(backend: str) -> CapabilityDiagnostic:
    diag = get_backend_capability(backend)

    if not diag.available:
        return diag

    import_name = _BACKEND_IMPORT_MAP.get(backend, f"holoviews.plotting.{backend}")
    try:
        __import__(import_name)
    except Exception as e:
        return diag.with_error(
            CapabilityStatus.IMPORT_ERROR,
            f"Failed to import {import_name}: {type(e).__name__}: {e}",
            (
                f"Check that {diag.package_name} is properly installed.",
                "Try reinstalling: pip install --force-reinstall " + (diag.package_name or backend),
                "Check for conflicting versions of dependencies.",
            ),
        )

    return diag


def import_datashader() -> CapabilityDiagnostic:
    diag = get_datashader_capability()
    if not diag.available:
        return diag
    try:
        import datashader
    except Exception as e:
        return diag.with_error(
            CapabilityStatus.IMPORT_ERROR,
            f"Failed to import datashader: {type(e).__name__}: {e}",
            (
                "Check that datashader is properly installed.",
                "Try reinstalling: pip install --force-reinstall datashader",
                "Check for conflicting dependency versions (e.g. numba, numpy).",
            ),
        )
    return diag


def is_backend_available(backend: str) -> bool:
    return get_backend_capability(backend).available


def is_datashader_available() -> bool:
    return get_datashader_capability().available


def is_static_export_available(fmt: str, backend: str | None = None) -> bool:
    caps = get_static_export_capabilities(backend)
    return fmt in caps and caps[fmt].available


def is_notebook_environment() -> bool:
    try:
        ip = get_ipython()  # type: ignore[name-defined]
        return hasattr(ip, "kernel")
    except Exception:
        return False


def list_available_backends() -> list[str]:
    return [bk for bk in _BACKEND_PACKAGE_MAP if is_backend_available(bk)]


def list_available_static_exports(backend: str | None = None) -> list[str]:
    caps = get_static_export_capabilities(backend)
    return [fmt for fmt, diag in caps.items() if diag.available]


def diagnose_all() -> str:
    all_caps = get_all_capabilities()
    lines = ["HoloViews Capability Diagnostics", "=" * 40, ""]

    lines.append("Plotting Backends:")
    for name, diag in all_caps["backends"].items():  # type: ignore[union-attr]
        status_icon = "✓" if diag.available else "✗"
        version_str = f" (v{diag.version})" if diag.version else ""
        lines.append(f"  {status_icon} {name}{version_str}")
        if not diag.available and diag.error_message:
            lines.append(f"      {diag.error_message}")
            for suggestion in diag.fix_suggestions:
                lines.append(f"      → {suggestion}")
    lines.append("")

    ds_diag = all_caps["datashader"]
    lines.append("Datashader Support:")
    status_icon = "✓" if ds_diag.available else "✗"  # type: ignore[union-attr]
    version_str = f" (v{ds_diag.version})" if ds_diag.version else ""  # type: ignore[union-attr]
    lines.append(f"  {status_icon} datashader{version_str}")
    if not ds_diag.available and ds_diag.error_message:  # type: ignore[union-attr]
        lines.append(f"      {ds_diag.error_message}")  # type: ignore[union-attr]
        for suggestion in ds_diag.fix_suggestions:  # type: ignore[union-attr]
            lines.append(f"      → {suggestion}")
    lines.append("")

    lines.append("Notebook Support:")
    for name, diag in all_caps["notebook"].items():  # type: ignore[union-attr]
        status_icon = "✓" if diag.available else "✗"
        version_str = f" (v{diag.version})" if diag.version else ""
        lines.append(f"  {status_icon} {name}{version_str}")
    lines.append("")

    lines.append("Static Export Formats:")
    for name, diag in all_caps["static_export"].items():  # type: ignore[union-attr]
        status_icon = "✓" if diag.available else "✗"
        backends = diag.details.get("available_backends", [])
        backend_str = f" [{', '.join(backends)}]" if backends else ""
        lines.append(f"  {status_icon} {name}{backend_str}")
        if not diag.available and diag.error_message:
            for bk_name, bk_detail in diag.details.get("per_backend", {}).items():
                if not bk_detail.get("backend_available", True):
                    lines.append(f"      {bk_name}: backend not available")
                elif bk_detail.get("missing_packages"):
                    lines.append(
                        f"      {bk_name}: missing {', '.join(bk_detail['missing_packages'])}"
                    )
                if bk_detail.get("missing_binary"):
                    lines.append(f"      {bk_name}: missing binary '{bk_detail['missing_binary']}'")
                if bk_detail.get("missing_webdriver"):
                    lines.append(f"      {bk_name}: missing webdriver")
        if not diag.available:
            for suggestion in diag.fix_suggestions[:3]:
                lines.append(f"      → {suggestion}")
    lines.append("")

    lines.append("Optional Extras (pyproject.toml):")
    for name, diag in all_caps["extras"].items():  # type: ignore[union-attr]
        if not name.startswith("extra_"):
            continue
        status_icon = "✓" if diag.available else "✗"
        missing = diag.details.get("missing", [])
        missing_str = f" (missing: {', '.join(missing)})" if missing else ""
        lines.append(f"  {status_icon} {name}{missing_str}")
    lines.append("")

    lines.append("CI Groups:")
    for name, diag in all_caps["ci_groups"].items():  # type: ignore[union-attr]
        status_icon = "✓" if diag.available else "✗"
        desc = diag.details.get("description", "")
        missing = diag.details.get("missing_backends", [])
        missing_str = f" (missing backends: {', '.join(missing)})" if missing else ""
        lines.append(f"  {status_icon} {name}: {desc}{missing_str}")
    lines.append("")

    lines.append(f"Current environment: {'notebook' if is_notebook_environment() else 'script/console'}")
    lines.append(f"Python version: {sys.version.split()[0]}")

    return "\n".join(lines)


__all__ = [
    "CapabilityDiagnostic",
    "CapabilityError",
    "CapabilityStatus",
    "CapabilityType",
    "diagnose_all",
    "get_all_capabilities",
    "get_backend_capability",
    "get_backend_static_export_capability",
    "get_ci_group_capabilities",
    "get_datashader_capability",
    "get_extra_capabilities",
    "get_notebook_capabilities",
    "get_static_export_capabilities",
    "import_backend",
    "import_datashader",
    "is_backend_available",
    "is_datashader_available",
    "is_notebook_environment",
    "is_static_export_available",
    "list_available_backends",
    "list_available_static_exports",
    "require_backend",
    "require_datashader",
    "require_static_export",
]
