from __future__ import annotations

import enum
import sys
import typing as t
from dataclasses import dataclass, field, replace
from functools import cache

from .dependencies import _LazyModule, _is_installed, _no_import_version, _re_no

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

    def with_error(self, status: CapabilityStatus, error_message: str, fix_suggestions: tuple[str, ...] | None = None) -> CapabilityDiagnostic:
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

_STATIC_EXPORT_FORMATS = {
    "png": {"bokeh": None, "matplotlib": None, "plotly": None},
    "svg": {"bokeh": None, "matplotlib": None, "plotly": None},
    "pdf": {"bokeh": None, "matplotlib": None, "plotly": None},
    "html": {"bokeh": None, "matplotlib": None, "plotly": None},
    "gif": {"bokeh": None, "matplotlib": None, "plotly": None},
    "mp4": {"bokeh": None, "matplotlib": None, "plotly": None},
    "webm": {"bokeh": None, "matplotlib": None, "plotly": None},
}


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


def _diagnose_static_export(backend: str | None = None) -> dict[str, CapabilityDiagnostic]:
    results: dict[str, CapabilityDiagnostic] = {}
    backends_to_check = [backend] if backend else list(_BACKEND_PACKAGE_MAP.keys())

    for fmt in _STATIC_EXPORT_FORMATS:
        fmt_backends = _STATIC_EXPORT_FORMATS[fmt]
        available_backends = []
        unavailable_backends = []

        for bk in backends_to_check:
            if bk not in fmt_backends:
                continue

            backend_diag = get_backend_capability(bk)
            if backend_diag.available:
                available_backends.append(bk)
            else:
                unavailable_backends.append(bk)

        status = CapabilityStatus.AVAILABLE if available_backends else CapabilityStatus.NOT_INSTALLED
        error_message = None if available_backends else f"No backend supports {fmt} export."

        results[fmt] = CapabilityDiagnostic(
            name=f"static_export_{fmt}",
            type=CapabilityType.STATIC_EXPORT,
            status=status,
            package_name=None,
            error_message=error_message,
            details={
                "format": fmt,
                "available_backends": available_backends,
                "unavailable_backends": unavailable_backends,
            },
            fix_suggestions=(
                f"Install one of these backends: {', '.join(unavailable_backends)}",
            ) if unavailable_backends else (),
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


def get_all_capabilities() -> dict[str, CapabilityDiagnostic | dict[str, CapabilityDiagnostic]]:
    return {
        "backends": {bk: get_backend_capability(bk) for bk in _BACKEND_PACKAGE_MAP},
        "datashader": get_datashader_capability(),
        "notebook": get_notebook_capabilities(),
        "static_export": get_static_export_capabilities(),
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


def is_notebook_environment() -> bool:
    try:
        ip = get_ipython()  # type: ignore[name-defined]
        return hasattr(ip, "kernel")
    except Exception:
        return False


def list_available_backends() -> list[str]:
    return [bk for bk in _BACKEND_PACKAGE_MAP if is_backend_available(bk)]


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
    lines.append("")

    lines.append(f"Current environment: {'notebook' if is_notebook_environment() else 'script/console'}")

    return "\n".join(lines)


__all__ = [
    "CapabilityDiagnostic",
    "CapabilityError",
    "CapabilityStatus",
    "CapabilityType",
    "diagnose_all",
    "get_all_capabilities",
    "get_backend_capability",
    "get_datashader_capability",
    "get_notebook_capabilities",
    "get_static_export_capabilities",
    "import_backend",
    "import_datashader",
    "is_backend_available",
    "is_datashader_available",
    "is_notebook_environment",
    "list_available_backends",
    "require_backend",
    "require_datashader",
]
