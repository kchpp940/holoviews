from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import util
from .dimension import Dimension, dimension_name


# ---------------------------------------------------------------------------
# Backend capability declarations: which formatter kinds does each backend
# support natively?  Anything not supported must either be applied server-side
# (pre-format values before writing to the data layer) or gracefully degrade.
# ---------------------------------------------------------------------------

FORMATTER_KIND_NONE = "none"
FORMATTER_KIND_STR_FORMAT = "str_format"      # e.g. "{:.2f}"
FORMATTER_KIND_PERCENT = "percent"            # e.g. "%.2f"
FORMATTER_KIND_CALLABLE = "callable"          # Python function
FORMATTER_KIND_BOKEH_NATIVE = "bokeh_native"  # printf, numeral, datetime

_BACKEND_FORMATTER_CAPABILITIES: dict[str, set[str]] = {
    "bokeh": {
        FORMATTER_KIND_NONE,
        FORMATTER_KIND_BOKEH_NATIVE,
        # str_format / percent / callable are applied via the Python layer
        # when rendering *values* for the legend / export path.  The
        # Bokeh HoverTool formatters dict only accepts native strings.
    },
    "plotly": {
        FORMATTER_KIND_NONE,
        FORMATTER_KIND_STR_FORMAT,   # Plotly accepts d3-style format strings
        FORMATTER_KIND_PERCENT,
        # callable formatters cannot be shipped to the browser; they are
        # flagged as unsupported so the caller can pre-format if needed.
    },
    "matplotlib": {
        FORMATTER_KIND_NONE,
        FORMATTER_KIND_STR_FORMAT,
        FORMATTER_KIND_PERCENT,
        FORMATTER_KIND_CALLABLE,     # runs in-process for legend / coord fmt
    },
}


def _classify_formatter(formatter: Any) -> str:
    """Classify a formatter value into one of the FORMATTER_KIND_* constants."""
    if formatter is None:
        return FORMATTER_KIND_NONE
    if callable(formatter):
        return FORMATTER_KIND_CALLABLE
    if isinstance(formatter, str):
        if formatter in {"printf", "numeral", "datetime"}:
            return FORMATTER_KIND_BOKEH_NATIVE
        if "%" in formatter and not re.search(r"\{[^}]*\}", formatter):
            return FORMATTER_KIND_PERCENT
        if re.search(r"\{[^}]*\}", formatter):
            return FORMATTER_KIND_STR_FORMAT
        return FORMATTER_KIND_STR_FORMAT  # best-effort fallback
    return FORMATTER_KIND_NONE


@dataclass(frozen=True)
class HoverFormatterSupport:
    """Capability declaration for a single field's formatter across backends."""

    kind: str
    bokeh: bool
    plotly: bool
    matplotlib: bool

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "supported": {
                "bokeh": self.bokeh,
                "plotly": self.plotly,
                "matplotlib": self.matplotlib,
            },
        }


@dataclass(frozen=True)
class HoverFieldSpec:
    """Immutable specification for a single hover field after resolution.

    Attributes
    ----------
    raw : str, Dimension, or dim
        The original field specification provided by the user.
    canonical_name : str
        Stable internal name (never sanitized, never collides).
    sanitized_name : str
        Bokeh ColumnDataSource compatible column key (sanitized).
    label : str
        Display label for tooltip / legend (respects aliases, units).
    formatter : callable or str or None
        Resolved formatter (from hover_formatters or Dimension.value_format).
    formatter_support : HoverFormatterSupport
        Per-backend capability declaration for this field's formatter.
    is_derived : bool
        True if this field is a dim() expression with ops (computed field).
    dimension_name : str or None
        If the field maps to a real Dimension, its name; None otherwise.
    """

    raw: Any
    canonical_name: str
    sanitized_name: str
    label: str
    formatter: Any
    formatter_support: HoverFormatterSupport
    is_derived: bool
    dimension_name: str | None


def _build_formatter_support(formatter: Any) -> HoverFormatterSupport:
    kind = _classify_formatter(formatter)
    return HoverFormatterSupport(
        kind=kind,
        bokeh=kind in _BACKEND_FORMATTER_CAPABILITIES["bokeh"],
        plotly=kind in _BACKEND_FORMATTER_CAPABILITIES["plotly"],
        matplotlib=kind in _BACKEND_FORMATTER_CAPABILITIES["matplotlib"],
    )


def _clean_dim_str(expr_str: str) -> str:
    """Remove redundant parentheses around simple dim references."""
    return re.sub(r"\((dim\([^)]+\))\)", r"\1", expr_str)


class HoverResolver:
    """Resolves ``hover_fields`` / ``hover_formatters`` / ``hover_aliases``
    declarations into a list of :class:`HoverFieldSpec` objects plus
    backend-specific output helpers and export metadata.

    One resolver is created (and cached) per element; tooltip, customdata,
    legend label and the exported ``hv.save`` metadata all consume the same
    resolved specs, including capability-aware formatter declarations.
    """

    _DERIVED_PREFIX = "_hv_derived_"
    METADATA_KEY = "holoviews:hover"

    def __init__(self, element):
        self._element = element
        self._specs: list[HoverFieldSpec] | None = None
        self._data: dict[str, np.ndarray] | None = None

    # ------------------------------------------------------------------
    # Public resolution API
    # ------------------------------------------------------------------

    def resolve(self) -> list[HoverFieldSpec]:
        """Return the resolved list of hover field specs (cached)."""
        if self._specs is not None:
            return self._specs

        from ..util.transform import dim

        element = self._element
        raw_fields = element.hover_fields
        if raw_fields is None:
            raw_fields = list(element.kdims) + list(element.vdims)

        specs: list[HoverFieldSpec] = []
        derived_idx = 0
        used_sanitized: dict[str, int] = {}

        for f in raw_fields:
            if isinstance(f, (str, Dimension)):
                existing = element.get_dimension(f)
                field = existing if existing is not None else f
            elif isinstance(f, dim):
                field = f
            else:
                field = f

            canonical = self._canonical_name(field)
            is_derived = isinstance(field, dim) and len(field.ops) > 0

            if is_derived:
                safe = f"{self._DERIVED_PREFIX}{derived_idx}"
                derived_idx += 1
            else:
                safe = util.dimension_sanitizer(canonical)

            if safe in used_sanitized:
                used_sanitized[safe] += 1
                safe = f"{safe}_{used_sanitized[safe]}"
            else:
                used_sanitized[safe] = 0

            label = self._resolve_label(field)
            formatter = self._resolve_formatter(field)
            support = _build_formatter_support(formatter)

            if isinstance(field, Dimension):
                dim_name = field.name
            elif isinstance(field, str):
                dim_obj = element.get_dimension(field)
                dim_name = dim_obj.name if dim_obj is not None else None
            elif isinstance(field, dim) and len(field.ops) == 0:
                dim_name = dimension_name(field.dimension)
            else:
                dim_name = None

            specs.append(
                HoverFieldSpec(
                    raw=field,
                    canonical_name=canonical,
                    sanitized_name=safe,
                    label=label,
                    formatter=formatter,
                    formatter_support=support,
                    is_derived=is_derived,
                    dimension_name=dim_name,
                )
            )

        self._specs = specs
        return self._specs

    def data(self) -> dict[str, np.ndarray]:
        """Return ``{sanitized_name: values_array}`` (cached)."""
        if self._data is not None:
            return self._data

        from ..util.transform import dim

        element = self._element
        result: dict[str, np.ndarray] = {}
        for spec in self.resolve():
            try:
                if isinstance(spec.raw, dim):
                    values = spec.raw.apply(element, flat=True)
                elif isinstance(spec.raw, Dimension):
                    values = element.dimension_values(
                        spec.raw.name, expanded=True, flat=True
                    )
                elif isinstance(spec.raw, str):
                    existing = element.get_dimension(spec.raw)
                    if existing is not None:
                        values = element.dimension_values(
                            existing.name, expanded=True, flat=True
                        )
                    elif spec.raw in element.cdims:
                        values = np.array([element.cdims[spec.raw]])
                    else:
                        continue
                else:
                    continue
                result[spec.sanitized_name] = values
            except (KeyError, ValueError):
                pass

        self._data = result
        return self._data

    # ------------------------------------------------------------------
    # Capability / backend helpers
    # ------------------------------------------------------------------

    def capability_matrix(self) -> dict[str, dict]:
        """Return a JSON-serializable capability summary.

        Example output::

            {
                "x": {"kind": "str_format",
                      "supported": {"bokeh": false, "plotly": true,
                                    "matplotlib": true}},
                "_hv_derived_0": {"kind": "callable", ...},
            }
        """
        return {
            spec.sanitized_name: spec.formatter_support.to_dict()
            for spec in self.resolve()
        }

    def supports_formatter(self, spec: HoverFieldSpec, backend: str) -> bool:
        """Return True if ``backend`` can apply ``spec.formatter`` natively."""
        return getattr(spec.formatter_support, backend, False)

    # ------------------------------------------------------------------
    # Value formatting helpers (used by legend, export, MPL coord, etc.)
    # ------------------------------------------------------------------

    def format_value(self, spec: HoverFieldSpec, value: Any) -> str:
        """Format a single value using the spec's formatter.

        Always works regardless of backend support — runs on the Python side.
        """
        fmt = spec.formatter

        if fmt is None:
            if isinstance(value, float) and np.isnan(value):
                return "NaN"
            return str(value)

        if callable(fmt):
            try:
                return fmt(value)
            except Exception:
                return str(value)

        if isinstance(fmt, str):
            if re.findall(r"\{[^}]*\}", fmt):
                try:
                    return fmt.format(value)
                except (TypeError, ValueError):
                    pass
            try:
                return fmt % value
            except (TypeError, ValueError):
                pass

        return str(value)

    # ------------------------------------------------------------------
    # Legend helpers (shared across all three backends)
    # ------------------------------------------------------------------

    def get_legend_label(self, dimension: Dimension | str) -> str:
        """Return the display label for a *dimension* in a legend.

        Works even when ``hover_fields`` is ``None`` (i.e. no explicit hover
        config) — alias lookup still happens against ``hover_aliases``.
        """
        element = self._element
        if isinstance(dimension, str):
            dim_obj = element.get_dimension(dimension)
            if dim_obj is None:
                return dimension
            dimension = dim_obj

        alias = self._lookup_alias(dimension, element.hover_aliases)
        if alias is not None:
            return alias

        return dimension.pprint_label

    def get_legend_formatted_value(self, dimension: Dimension | str, value: Any) -> str:
        """Format a value for legend display, respecting hover_formatters."""
        element = self._element
        if isinstance(dimension, str):
            dim_obj = element.get_dimension(dimension)
            if dim_obj is None:
                return str(value)
            dimension = dim_obj

        fmt = self._lookup_alias(dimension, element.hover_formatters)
        if fmt is None and dimension.value_format:
            fmt = dimension.value_format

        if fmt is None:
            return str(value)
        if callable(fmt):
            try:
                return fmt(value)
            except Exception:
                return str(value)
        if isinstance(fmt, str):
            if re.findall(r"\{[^}]*\}", fmt):
                try:
                    return fmt.format(value)
                except (TypeError, ValueError):
                    pass
            try:
                return fmt % value
            except (TypeError, ValueError):
                pass
        return str(value)

    # ------------------------------------------------------------------
    # Backend-specific output helpers
    # ------------------------------------------------------------------

    def to_bokeh_tooltips(self) -> list[tuple[str, str]]:
        """Return ``[(label, '@{sanitized}'), ...]`` for Bokeh HoverTool."""
        return [
            (spec.label, f"@{{{spec.sanitized_name}}}")
            for spec in self.resolve()
        ]

    def to_bokeh_formatters(self) -> dict[str, str]:
        """Return Bokeh HoverTool ``formatters`` dict.

        Only *natively supported* formatter kinds (printf, numeral, datetime)
        are included; callable / %-style formatters cannot be passed to the
        Bokeh HoverTool and must be applied server-side.
        """
        result: dict[str, str] = {}
        for spec in self.resolve():
            if spec.formatter_support.kind == FORMATTER_KIND_BOKEH_NATIVE:
                result[f"@{{{spec.sanitized_name}}}"] = spec.formatter
        return result

    def to_bokeh_legend_kwargs(self, dimension: Dimension) -> dict[str, Any]:
        """Return kwargs suitable for a Bokeh legend entry.

        Currently returns ``{"label": alias_or_pprint_label}``; kept as a
        dedicated method so future extensions (e.g. per-item value
        formatting) stay in one place.
        """
        return {"label": self.get_legend_label(dimension)}

    def to_plotly_customdata(self):
        """Return ``(customdata_array, ordered_specs, column_metadata)``.

        ``column_metadata`` is a list of per-column dicts containing
        ``label``, ``formatter_kind`` and ``formatter_supported`` flags, so
        downstream code knows whether the value still needs formatting.
        """
        d = self.data()
        specs = self.resolve()
        ordered = [s for s in specs if s.sanitized_name in d]
        if not ordered:
            return None, [], []
        arrays = [d[s.sanitized_name] for s in ordered]
        try:
            customdata = np.column_stack(arrays)
        except (ValueError, TypeError):
            customdata = None
        meta = [
            {
                "label": s.label,
                "dimension": s.dimension_name,
                "formatter_kind": s.formatter_support.kind,
                "formatter_supported": {
                    "bokeh": s.formatter_support.bokeh,
                    "plotly": s.formatter_support.plotly,
                    "matplotlib": s.formatter_support.matplotlib,
                },
                "needs_python_formatting": (
                    s.formatter is not None
                    and s.formatter_support.kind == FORMATTER_KIND_CALLABLE
                ),
                "is_derived": s.is_derived,
            }
            for s in ordered
        ]
        return customdata, ordered, meta

    def to_plotly_hovertemplate(self, ordered_specs: list[HoverFieldSpec]) -> str | None:
        """Return a Plotly ``hovertemplate`` string.

        Callable formatters cannot ship to the browser; they are flagged in
        the column metadata so the caller knows to pre-format values into a
        string column if exact formatting is required.
        """
        if not ordered_specs:
            return None

        parts: list[str] = []
        for i, spec in enumerate(ordered_specs):
            fmt = spec.formatter
            if (
                fmt is not None
                and spec.formatter_support.plotly
                and spec.formatter_support.kind != FORMATTER_KIND_CALLABLE
            ):
                parts.append(f"<b>{spec.label}</b>: %{{customdata[{i}]:{fmt}}}")
            else:
                parts.append(f"<b>{spec.label}</b>: %{{customdata[{i}]}}")
        return "<br>".join(parts) + "<extra></extra>"

    def to_mpl_format_coord(self):
        """Return a ``format_coord(x, y)`` function for Matplotlib."""
        element = self._element
        d = self.data()
        specs = self.resolve()
        ordered = [s for s in specs if s.sanitized_name in d]
        if not ordered:
            return None

        n_points = len(next(iter(d.values())))
        if not n_points:
            return None

        try:
            xdim = element.get_dimension(0)
            ydim = element.get_dimension(1)
            x_spec = self._find_spec_by_dim(xdim) if xdim else None
            y_spec = self._find_spec_by_dim(ydim) if ydim else None
        except Exception:
            x_spec = None
            y_spec = None

        xvalues = d[x_spec.sanitized_name] if x_spec and x_spec.sanitized_name in d else None
        yvalues = d[y_spec.sanitized_name] if y_spec and y_spec.sanitized_name in d else None

        resolver = self

        def format_coord(x, y):
            parts: list[str] = []
            if xvalues is not None and yvalues is not None and len(xvalues) == len(yvalues):
                distances = (xvalues - x) ** 2 + (yvalues - y) ** 2
                idx = int(np.argmin(distances))
                if 0 <= idx < n_points:
                    for spec in ordered:
                        value = d[spec.sanitized_name][idx]
                        formatted = resolver.format_value(spec, value)
                        parts.append(f"{spec.label}={formatted}")
            if not parts:
                parts = [f"x={x:.6g}", f"y={y:.6g}"]
            return ", ".join(parts)

        return format_coord

    # ------------------------------------------------------------------
    # Export / serialization
    # ------------------------------------------------------------------

    def get_export_spec(self) -> dict:
        """Return the full capability-aware export specification.

        This dict is written into the renderer state / saved output so that
        downstream consumers (``hv.save``, panel, etc.) have access to the
        exact same label / formatter / capability information as the live
        backends.

        The returned dict is safe for JSON serialization.
        """
        specs = self.resolve()
        return {
            "version": 1,
            "backend_capabilities": {
                backend: sorted(list(kinds))
                for backend, kinds in _BACKEND_FORMATTER_CAPABILITIES.items()
            },
            "fields": [
                {
                    "canonical_name": s.canonical_name,
                    "sanitized_name": s.sanitized_name,
                    "label": s.label,
                    "dimension": s.dimension_name,
                    "is_derived": s.is_derived,
                    "formatter": {
                        "kind": s.formatter_support.kind,
                        "value": (
                            s.formatter
                            if isinstance(s.formatter, (str, type(None)))
                            else f"<callable: {getattr(s.formatter, '__name__', type(s.formatter).__name__)}>"
                        ),
                        "supported": {
                            "bokeh": s.formatter_support.bokeh,
                            "plotly": s.formatter_support.plotly,
                            "matplotlib": s.formatter_support.matplotlib,
                        },
                    },
                }
                for s in specs
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        """Shorthand alias for :meth:`get_export_spec`.

        Backward-compatible with the earlier minimal dict-based export.
        """
        return self.get_export_spec()

    def attach_metadata(self, backend: str, state: Any) -> Any:
        """Attach the resolved hover metadata to a backend figure ``state``.

        - **bokeh**: appends a dict tag to ``state.tags``
        - **plotly**: writes ``state['layout']['metadata'][METADATA_KEY]``
        - **matplotlib**: sets ``state._hv_hover_metadata`` attribute

        Returns the (possibly mutated) ``state``.
        """
        spec = self.get_export_spec()
        payload = {self.METADATA_KEY: spec}

        if backend == "bokeh":
            if hasattr(state, "tags"):
                state.tags = list(state.tags) + [payload]
        elif backend == "plotly":
            if isinstance(state, dict):
                layout = state.setdefault("layout", {})
                metadata = layout.setdefault("metadata", {})
                if isinstance(metadata, dict):
                    metadata.update(payload)
        elif backend == "matplotlib":
            try:
                state._hv_hover_metadata = spec
            except Exception:
                pass
        return state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_spec_by_dim(self, dim_obj: Dimension) -> HoverFieldSpec | None:
        for spec in self.resolve():
            if isinstance(spec.raw, Dimension) and spec.raw == dim_obj:
                return spec
            if isinstance(spec.raw, str) and spec.raw == dim_obj.name:
                return spec
        return None

    @staticmethod
    def _canonical_name(field) -> str:
        from ..util.transform import dim

        if isinstance(field, dim):
            if len(field.ops) == 0:
                return dimension_name(field.dimension)
            return str(field)
        elif isinstance(field, Dimension):
            return field.name
        elif isinstance(field, str):
            return field
        else:
            return str(field)

    def _resolve_label(self, field) -> str:
        from ..util.transform import dim

        element = self._element
        alias = self._lookup_alias(field, element.hover_aliases)
        if alias is not None:
            return alias

        canonical = self._canonical_name(field)

        if isinstance(field, Dimension):
            return field.pprint_label
        elif isinstance(field, dim):
            if len(field.ops) == 0:
                dim_obj = element.get_dimension(field.dimension)
                if dim_obj is not None:
                    return dim_obj.pprint_label
                return dimension_name(field.dimension)
            return canonical
        elif isinstance(field, str):
            dim_obj = element.get_dimension(field)
            if dim_obj is not None:
                return dim_obj.pprint_label
            return field
        else:
            return canonical

    def _resolve_formatter(self, field):
        from ..util.transform import dim

        element = self._element
        fmt = self._lookup_alias(field, element.hover_formatters)
        if fmt is not None:
            return fmt

        if isinstance(field, Dimension):
            if field.value_format:
                return field.value_format
        elif isinstance(field, str):
            dim_obj = element.get_dimension(field)
            if dim_obj is not None and dim_obj.value_format:
                return dim_obj.value_format
        return None

    def _lookup_alias(self, field, aliases: dict) -> Any | None:
        from ..util.transform import dim

        if not aliases:
            return None

        canonical = self._canonical_name(field)
        if canonical in aliases:
            return aliases[canonical]

        if isinstance(field, dim):
            for key in (repr(field), str(field), _clean_dim_str(str(field))):
                if key in aliases:
                    return aliases[key]

        return None
