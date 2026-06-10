from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import util
from .dimension import Dimension, dimension_name


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
    is_derived : bool
        True if this field is a dim() expression with ops (computed field).
    """

    raw: Any
    canonical_name: str
    sanitized_name: str
    label: str
    formatter: Any
    is_derived: bool


def _clean_dim_str(expr_str: str) -> str:
    """Remove redundant parentheses around simple dim references.

    ``dim('y')/(dim('x'))`` → ``dim('y')/dim('x')``
    """
    return re.sub(r"\((dim\([^)]+\))\)", r"\1", expr_str)


class HoverResolver:
    """Stateless resolver that turns hover_fields / hover_formatters /
    hover_aliases declarations into a list of :class:`HoverFieldSpec`
    objects plus backend-specific output helpers.

    The resolver is *created once* per element (and cached), so all three
    backends consume the *same* parsed result.

    Parameters
    ----------
    element : Dimensioned
        The HoloViews element that owns the hover configuration.
    """

    _DERIVED_PREFIX = "_hv_derived_"

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

            specs.append(
                HoverFieldSpec(
                    raw=field,
                    canonical_name=canonical,
                    sanitized_name=safe,
                    label=label,
                    formatter=formatter,
                    is_derived=is_derived,
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
    # Single-value helpers (used by legend, export, etc.)
    # ------------------------------------------------------------------

    def format_value(self, spec: HoverFieldSpec, value: Any) -> str:
        """Format a single value using the spec's formatter."""
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

    def get_legend_label(self, dimension: Dimension | str) -> str:
        """Return the display label for a *dimension* when used in legend.

        Looks up aliases first, then falls back to ``Dimension.pprint_label``.
        Works even when ``hover_fields`` is ``None`` (i.e. the element has no
        explicit hover config).
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

        Only string formatters that are Bokeh format specs (e.g. ``'printf'``,
        ``'numeral'``, ``'datetime'``) are included.  Python callable / format
        string formatters are applied server-side via
        :meth:`format_value` by the Matplotlib / export path.
        """
        result: dict[str, str] = {}
        bokeh_format_types = {"printf", "numeral", "datetime"}
        for spec in self.resolve():
            if isinstance(spec.formatter, str) and spec.formatter in bokeh_format_types:
                result[f"@{{{spec.sanitized_name}}}"] = spec.formatter
        return result

    def to_plotly_customdata(self):
        """Return ``(customdata_array, field_order)`` for Plotly traces."""
        d = self.data()
        specs = self.resolve()
        ordered = [s for s in specs if s.sanitized_name in d]
        if not ordered:
            return None, []
        arrays = [d[s.sanitized_name] for s in ordered]
        try:
            customdata = np.column_stack(arrays)
        except (ValueError, TypeError):
            customdata = None
        return customdata, ordered

    def to_plotly_hovertemplate(self, ordered_specs: list[HoverFieldSpec]) -> str | None:
        """Return a Plotly ``hovertemplate`` string.

        Callable formatters are *not* embedded (Plotly cannot execute Python);
        they are flagged so the caller knows to apply them client-side if needed.
        """
        if not ordered_specs:
            return None

        parts: list[str] = []
        for i, spec in enumerate(ordered_specs):
            fmt = spec.formatter
            if fmt is not None and not callable(fmt):
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

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the resolved state.

        This is useful for export pipelines that need to preserve the hover
        configuration without referencing the live element.
        """
        return {
            "fields": [
                {
                    "canonical_name": spec.canonical_name,
                    "sanitized_name": spec.sanitized_name,
                    "label": spec.label,
                    "is_derived": spec.is_derived,
                    "formatter_type": (
                        "callable"
                        if callable(spec.formatter)
                        else type(spec.formatter).__name__
                        if spec.formatter is not None
                        else None
                    ),
                }
                for spec in self.resolve()
            ]
        }

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
