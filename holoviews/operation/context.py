from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple, Dict, List, Union

import numpy as np

from ..core import Dataset
from ..core.util import datetime_types, dt_to_int, isfinite, max_range


SamplingMetadata = Dict[str, Any]
ProductMetadata = Dict[str, Any]
ArtifactDict = Dict[str, Any]


def _get_operation_params(operation: Any) -> Any:
    """Safe accessor for operation params; works with or without `p` set."""
    if hasattr(operation, 'p'):
        return operation.p
    return operation


def _get_pixel_ratio_from_operation(ctx: "OperationExecutionContext") -> float:
    """Resolve pixel_ratio, with fallback to operation._get_pixel_ratio() and panel state."""
    if hasattr(ctx, '_operation') and hasattr(ctx._operation, '_get_pixel_ratio'):
        return ctx._operation._get_pixel_ratio()
    if ctx.pixel_ratio is not None:
        return ctx.pixel_ratio
    try:
        from panel import state
        if state.browser_info and isinstance(
            state.browser_info.device_pixel_ratio, (int, float)
        ):
            return state.browser_info.device_pixel_ratio
    except Exception:
        pass
    return 1.0


@dataclass
class OperationExecutionContext:
    """Neutral, standalone execution context shared by resample/rasterize/datashade.

    This context consolidates all state that was previously scattered across
    operation/resample.py, operation/datashader.py and the DynamicMap/renderer
    call chain:
      - Input element and dimension configuration
      - Range clipping  (x_range, y_range, expand, target)
      - Pixel dimensions (width, height, pixel_ratio)
      - Sampling limits  (x_sampling, y_sampling)
      - Unit & coordinate computation (xunit, yunit, xs, ys)
      - Datatype detection (xtype, ytype) and datetime transformations
      - Bounds derivation
      - Precompute / cache coordination (precomputed, use_precompute, plot_id)
      - Sampling metadata and output-product metadata (sampling_meta, product_meta)
      - Arbitrary artifacts for cross-operation data passing (artifacts)

    Resample, rasterize and datashade all create contexts through the same
    ``.create()`` factory and consume fields through the same dataclass,
    instead of each operation rebuilding its own ad-hoc state tuple.
    """

    # ------------------------------------------------------------------
    # 1. Input configuration
    # ------------------------------------------------------------------
    element: Any
    x_dim: Optional[Any] = None
    y_dim: Optional[Any] = None
    ndim: int = 2
    default_y_range: Optional[Tuple[float, float]] = None

    # ------------------------------------------------------------------
    # 2. Range clipping & target
    # ------------------------------------------------------------------
    x_range: Optional[Tuple[float, float]] = None
    y_range: Optional[Tuple[float, float]] = None
    expand: bool = True
    target: Optional[Dataset] = None

    # ------------------------------------------------------------------
    # 3. Pixel dimensions
    # ------------------------------------------------------------------
    width: int = 400
    height: int = 400
    pixel_ratio: float = 1.0

    # ------------------------------------------------------------------
    # 4. Sampling limits (sampling resolution)
    # ------------------------------------------------------------------
    x_sampling: Optional[float] = None
    y_sampling: Optional[float] = None

    # ------------------------------------------------------------------
    # 5. Derived unit & coordinate data
    # ------------------------------------------------------------------
    xunit: float = 0.0
    yunit: float = 0.0
    xs: Optional[np.ndarray] = None
    ys: Optional[np.ndarray] = None
    xtype: str = "numeric"
    ytype: str = "numeric"

    # ------------------------------------------------------------------
    # 6. Datetime transformations
    # ------------------------------------------------------------------
    x_range_dt: Optional[Tuple[Any, Any]] = None
    y_range_dt: Optional[Tuple[Any, Any]] = None
    xs_dt: Optional[np.ndarray] = None
    ys_dt: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # 7. Bounds
    # ------------------------------------------------------------------
    bounds: Optional[Tuple[float, float, float, float]] = None

    # ------------------------------------------------------------------
    # 8. Precompute / cache
    # ------------------------------------------------------------------
    use_precompute: bool = False
    precomputed: Dict[Any, Any] = field(default_factory=dict)
    plot_id: Optional[Any] = None

    # ------------------------------------------------------------------
    # 9. Sampling metadata (sampling resolution diagnostics)
    # ------------------------------------------------------------------
    sampling_meta: SamplingMetadata = field(default_factory=dict)

    # ------------------------------------------------------------------
    # 10. Output product metadata (passed back through result metadata)
    # ------------------------------------------------------------------
    product_meta: ProductMetadata = field(default_factory=dict)

    # ------------------------------------------------------------------
    # 11. Arbitrary artifacts (cross-operation data passing)
    # ------------------------------------------------------------------
    artifacts: ArtifactDict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # 12. Backward-compat "metadata" bag (kept for external consumers)
    # ------------------------------------------------------------------
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ------ internals (not part of public API) -------------------------
    def __post_init__(self):
        # `_operation` is set by the factory; we don't advertise it in the
        # dataclass fields so the class stays serializable/inspectable.
        pass

    # ==================================================================
    # Factory
    # ==================================================================
    @classmethod
    def create(cls,
               operation: Any,
               element: Any,
               x_dim: Optional[Any] = None,
               y_dim: Optional[Any] = None,
               ndim: int = 2,
               default: Optional[Tuple[float, float]] = None,
               use_cache: bool = True) -> "OperationExecutionContext":
        """Create a fully-populated execution context.

        Parameters
        ----------
        operation : Operation
            The operation instance. Parameters are read from ``operation.p``
            (if set) or directly from the instance as fallback.
        element : Element
            The input element being processed.
        x_dim, y_dim : optional
            Dimension(s) to use; can be a single dimension or a list.
        ndim : {1, 2}
            Dimensionality of the rasterization (1D spikes vs 2D image).
        default : tuple, optional
            Default y-range fallback if not specified elsewhere.
        use_cache : bool
            Whether to attach the operation's ``_precomputed`` cache dict
            to this context.
        """
        p = _get_operation_params(operation)

        def get(name, default_val=None):
            return getattr(p, name, default_val)

        ctx = cls(
            element=element,
            x_dim=x_dim,
            y_dim=y_dim,
            ndim=ndim,
            default_y_range=default,
            x_range=get('x_range'),
            y_range=get('y_range'),
            expand=get('expand', True),
            target=get('target'),
            width=get('width', 400),
            height=get('height', 400),
            pixel_ratio=get('pixel_ratio'),
            x_sampling=get('x_sampling'),
            y_sampling=get('y_sampling'),
            use_precompute=get('precompute', False),
            precomputed=(getattr(operation, '_precomputed', {}) if use_cache else {}),
            plot_id=getattr(element, '_plot_id', None),
        )
        ctx._operation = operation

        ctx._compute_ranges()
        ctx._compute_dimensions()
        ctx._apply_pixel_ratio()
        ctx._apply_sampling_limits()
        ctx._compute_units_and_coords()
        ctx._compute_bounds()
        ctx._transform_datetimes()
        ctx._populate_sampling_metadata()

        return ctx

    # ==================================================================
    # 7-stage computation pipeline
    # ==================================================================

    def _compute_ranges(self) -> None:
        """Stage 1 – resolve x_range / y_range from target / params / data."""
        x = self.x_dim if isinstance(self.x_dim, list) else ([self.x_dim] if self.x_dim else None)
        y = self.y_dim if isinstance(self.y_dim, list) else ([self.y_dim] if self.y_dim else None)

        if self.target is not None:
            x0, y0, x1, y1 = self.target.bounds.lbrt()
            self.x_range = (x0, x1)
            self.y_range = (y0, y1)
            arr = self.target.dimension_values(2, flat=False)
            self.height, self.width = arr.shape
            return

        p_x_range = self.x_range
        if x is None:
            self.x_range = p_x_range or (-0.5, 0.5)
        elif self.expand or not p_x_range:
            if p_x_range and all(isfinite(v) for v in p_x_range):
                self.x_range = p_x_range
            else:
                self.x_range = max_range([self.element.range(xd) for xd in x])
        else:
            x0, x1 = p_x_range
            ex0, ex1 = max_range([self.element.range(xd) for xd in x])
            self.x_range = (
                np.nanmin([np.nanmax([x0, ex0]), ex1]),
                np.nanmax([np.nanmin([x1, ex1]), ex0]),
            )

        p_y_range = self.y_range
        if y is None and self.ndim == 2:
            self.y_range = p_y_range or self.default_y_range or (-0.5, 0.5)
        elif self.expand or not p_y_range:
            if p_y_range and all(isfinite(v) for v in p_y_range):
                self.y_range = p_y_range
            elif self.default_y_range is None and y is not None:
                self.y_range = max_range([self.element.range(yd) for yd in y])
            else:
                self.y_range = self.default_y_range
        else:
            y0, y1 = p_y_range
            if self.default_y_range is None and y is not None:
                ey0, ey1 = max_range([self.element.range(yd) for yd in y])
            else:
                ey0, ey1 = self.default_y_range or (0, 0)
            self.y_range = (
                np.nanmin([np.nanmax([y0, ey0]), ey1]),
                np.nanmax([np.nanmin([y1, ey1]), ey0]),
            )

    def _compute_dimensions(self) -> None:
        """Stage 2 – detect numeric vs datetime and coerce ranges to numeric."""
        xstart, xend = self.x_range

        if isinstance(xstart, str) or isinstance(xend, str):
            raise ValueError("Categorical data is not supported")
        elif isinstance(xstart, datetime_types) or isinstance(xend, datetime_types):
            xstart, xend = dt_to_int(xstart, "ns"), dt_to_int(xend, "ns")
            self.xtype = "datetime"
        elif not np.isfinite(xstart) and not np.isfinite(xend):
            xstart, xend = 0, 0
            x = self.x_dim[0] if isinstance(self.x_dim, list) else self.x_dim
            if x and self.element.get_dimension_type(x) in datetime_types:
                self.xtype = "datetime"

        if self.ndim == 2 and self.y_range is not None:
            ystart, yend = self.y_range
            if isinstance(ystart, str) or isinstance(yend, str):
                raise ValueError("Categorical data is not supported")
            elif isinstance(ystart, datetime_types) or isinstance(yend, datetime_types):
                ystart, yend = dt_to_int(ystart, "ns"), dt_to_int(yend, "ns")
                self.ytype = "datetime"
            elif not np.isfinite(ystart) and not np.isfinite(yend):
                ystart, yend = 0, 0
                y = self.y_dim[0] if isinstance(self.y_dim, list) else self.y_dim
                if y and self.element.get_dimension_type(y) in datetime_types:
                    self.ytype = "datetime"
            self.y_range = (ystart, yend)

        self.x_range = (xstart, xend)

    def _apply_pixel_ratio(self) -> None:
        """Stage 3 – scale width/height by pixel_ratio."""
        pr = _get_pixel_ratio_from_operation(self)
        self.pixel_ratio = pr
        self.width = int(self.width * pr)
        self.height = int(self.height * pr)

    def _apply_sampling_limits(self) -> None:
        """Stage 4 – apply x_sampling / y_sampling density caps."""
        xstart, xend = self.x_range
        xspan = xend - xstart
        if self.ndim == 2 and self.y_range is not None:
            ystart, yend = self.y_range
            yspan = yend - ystart
        else:
            yspan = 0

        if self.x_sampling and xspan > 0:
            self.width = int(min([(xspan / self.x_sampling), self.width]))
        if self.y_sampling and yspan > 0:
            self.height = int(min([(yspan / self.y_sampling), self.height]))

    def _compute_units_and_coords(self) -> None:
        """Stage 5 – compute xunit/yunit and pixel-centre coordinate arrays."""
        xstart, xend = self.x_range
        xspan = xend - xstart

        if self.ndim == 2 and self.y_range is not None:
            ystart, yend = self.y_range
            yspan = yend - ystart
        else:
            ystart, yend = 0, 0
            yspan = 0

        if xstart == xend or self.width == 0:
            self.xunit, self.width = 0, 0
        else:
            self.xunit = float(xspan) / self.width

        if ystart == yend or self.height == 0:
            self.yunit, self.height = 0, 0
        else:
            self.yunit = float(yspan) / self.height

        self.xs = (
            np.linspace(
                xstart + self.xunit / 2.0, xend - self.xunit / 2.0, self.width
            )
            if self.width > 0
            else np.array([])
        )
        self.ys = (
            np.linspace(
                ystart + self.yunit / 2.0, yend - self.yunit / 2.0, self.height
            )
            if self.height > 0
            else np.array([])
        )

    def _compute_bounds(self) -> None:
        """Stage 6 – compute ``(x0, y0, x1, y1)`` bounds tuple."""
        x0, x1 = self.x_range
        if self.ndim == 2 and self.y_range is not None:
            y0, y1 = self.y_range
        else:
            y0, y1 = 0, 0
        self.bounds = (x0, y0, x1, y1)

    def _transform_datetimes(self) -> None:
        """Stage 7 – cast integer datetimes back to datetime64 for output."""
        xstart, xend = self.x_range
        if self.ndim == 2 and self.y_range is not None:
            ystart, yend = self.y_range
        else:
            ystart, yend = 0, 0

        xs, ys = self.xs, self.ys

        if self.xtype == "datetime":
            xstart, xend = np.array([xstart, xend]).astype("datetime64[ns]")
            xs = xs.astype("datetime64[ns]") if xs is not None else None
        if self.ytype == "datetime":
            ystart, yend = np.array([ystart, yend]).astype("datetime64[ns]")
            ys = ys.astype("datetime64[ns]") if ys is not None else None

        self.x_range_dt = (xstart, xend)
        self.y_range_dt = (ystart, yend)
        self.xs_dt = xs
        self.ys_dt = ys

    def _populate_sampling_metadata(self) -> None:
        """Stage 8 – collect sampling-resolution diagnostics.

        The ``sampling_meta`` dict contains a stable, well-documented set of
        keys that renderers, DynamicMap streams and downstream operations
        can rely on without re-deriving from the element.
        """
        x0, x1 = self.x_range
        xspan = float(x1 - x0) if (x1 is not None and x0 is not None) else 0.0
        if self.ndim == 2 and self.y_range is not None:
            y0, y1 = self.y_range
            yspan = float(y1 - y0)
        else:
            y0, y1 = 0.0, 0.0
            yspan = 0.0

        eff_x_sampling = self.xunit if self.width > 0 else None
        eff_y_sampling = self.yunit if self.height > 0 else None

        self.sampling_meta = {
            "x_span": xspan,
            "y_span": yspan,
            "effective_x_sampling": eff_x_sampling,
            "effective_y_sampling": eff_y_sampling,
            "requested_x_sampling": self.x_sampling,
            "requested_y_sampling": self.y_sampling,
            "x_sampling_enforced": (
                self.x_sampling is not None
                and eff_x_sampling is not None
                and eff_x_sampling >= self.x_sampling * 0.999
            ),
            "y_sampling_enforced": (
                self.y_sampling is not None
                and eff_y_sampling is not None
                and eff_y_sampling >= self.y_sampling * 0.999
            ),
            "pixel_ratio_used": self.pixel_ratio,
            "output_shape": (self.height, self.width),
            "ndim": self.ndim,
            "xtype": self.xtype,
            "ytype": self.ytype,
        }

    # ==================================================================
    # Backward-compatibility helpers (consume as legacy tuples)
    # ==================================================================
    def get_sampling_result(self) -> Tuple[
        Tuple[Tuple[float, float], Tuple[float, float]],
        Tuple[np.ndarray, np.ndarray],
        Tuple[int, int],
        Tuple[str, str],
    ]:
        """Return the 4-tuple shape that ``_get_sampling()`` used to return."""
        return (
            (self.x_range, self.y_range),
            (self.xs, self.ys),
            (self.width, self.height),
            (self.xtype, self.ytype),
        )

    def get_dt_transform_result(self) -> Tuple[
        Tuple[Tuple[Any, Any], Tuple[Any, Any]],
        Tuple[Optional[np.ndarray], Optional[np.ndarray]],
    ]:
        """Return the 2-tuple shape that ``_dt_transform()`` used to return."""
        return (
            (self.x_range_dt, self.y_range_dt),
            (self.xs_dt, self.ys_dt),
        )

    # ==================================================================
    # Grid-state predicates
    # ==================================================================
    def is_empty(self) -> bool:
        """True if the derived grid has zero width or zero height."""
        return self.width == 0 or self.height == 0

    # ==================================================================
    # Precompute / cache API (also supports explicit keys)
    # ==================================================================
    def cache_result(self, key: Any = None, value: Any = None) -> None:
        """Persist ``value`` into the precomputed cache if enabled.

        Parameters
        ----------
        key : hashable, optional
            If omitted, ``self.plot_id`` is used.
        value : any
            The value to cache (e.g. triangulation, edge paths, glyph data).
        """
        cache_key = key if key is not None else self.plot_id
        if self.use_precompute and cache_key is not None:
            self.precomputed[cache_key] = value
            if hasattr(self, '_operation'):
                self._operation._precomputed = self.precomputed

    def get_cached(self, key: Any = None) -> Optional[Any]:
        """Retrieve a previously cached value, or ``None``."""
        cache_key = key if key is not None else self.plot_id
        if cache_key is not None and cache_key in self.precomputed:
            return self.precomputed[cache_key]
        return None

    def has_cached(self, key: Any = None) -> bool:
        """Whether a value is present for ``key`` (or ``plot_id`` by default)."""
        cache_key = key if key is not None else self.plot_id
        return cache_key is not None and cache_key in self.precomputed

    def invalidate_cache(self, key: Any = None) -> bool:
        """Remove an entry from the cache. Returns True if anything was removed."""
        cache_key = key if key is not None else self.plot_id
        if cache_key is not None and cache_key in self.precomputed:
            del self.precomputed[cache_key]
            return True
        return False

    # ==================================================================
    # Product metadata helpers
    # ==================================================================
    def set_product_meta(self, **kwargs: Any) -> None:
        """Atomically update product metadata (output-diagnostics bag)."""
        self.product_meta.update(kwargs)

    def get_product_meta(self, key: str, default: Any = None) -> Any:
        """Lookup a single product-metadata entry."""
        return self.product_meta.get(key, default)

    def attach_product_meta(self, element: Any) -> Any:
        """Attach ``product_meta`` onto an output element's ``.metadata`` dict.

        If the element has a ``metadata`` attribute (dict-like), the
        product_meta entries are merged in-place and the same element
        is returned.  If the element has no metadata attribute the
        element is returned unchanged.

        Returns the element so callers can simply chain:
        ``return ctx.attach_product_meta(result)``.
        """
        if not self.product_meta:
            return element
        if hasattr(element, 'metadata') and isinstance(element.metadata, dict):
            element.metadata.update(self.product_meta)
        return element

    # ==================================================================
    # Artifact helpers (for passing arbitrary data between operations)
    # ==================================================================
    def set_artifact(self, name: str, value: Any) -> None:
        """Store an arbitrary cross-operation artifact (e.g. computed glyph)."""
        self.artifacts[name] = value

    def get_artifact(self, name: str, default: Any = None) -> Any:
        """Fetch a stored artifact by name."""
        return self.artifacts.get(name, default)

    def has_artifact(self, name: str) -> bool:
        return name in self.artifacts

    # ==================================================================
    # Recompute helpers (for operations that mutate fields mid-process)
    # ==================================================================
    def recompute(self) -> None:
        """Re-run the computation pipeline (after mutating x_range/width/etc)."""
        self._compute_dimensions()
        self._apply_sampling_limits()
        self._compute_units_and_coords()
        self._compute_bounds()
        self._transform_datetimes()
        self._populate_sampling_metadata()

    def recompute_pixel_ratio(self) -> None:
        """Re-run only the pixel-ratio + downstream stages."""
        self._apply_pixel_ratio()
        self._apply_sampling_limits()
        self._compute_units_and_coords()
        self._compute_bounds()
        self._transform_datetimes()
        self._populate_sampling_metadata()


__all__ = [
    "OperationExecutionContext",
    "SamplingMetadata",
    "ProductMetadata",
    "ArtifactDict",
]
