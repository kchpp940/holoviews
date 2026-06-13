from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple, Union

import numpy as np
import param
from param.parameterized import bothmethod

from ..core import Dataset, Operation
from ..core.util import datetime_types, dt_to_int, isfinite, max_range
from ..element import Image
from ..streams import PlotSize, RangeX, RangeXY
from .guard import ExecutionGuardResult, OperationGuard


@dataclass
class OperationExecutionContext:
    """Unified execution context for resampling/rasterizing operations.

    Consolidates all sampling parameters, range calculations, pixel dimensions,
    and precomputation state that was previously scattered across
    ResampleOperation2D, AggregationOperation, and individual _process methods.
    """

    element: Any
    x_dim: Optional[Any] = None
    y_dim: Optional[Any] = None
    ndim: int = 2
    default_y_range: Optional[Tuple[float, float]] = None

    x_range: Optional[Tuple[float, float]] = None
    y_range: Optional[Tuple[float, float]] = None
    width: int = 400
    height: int = 400
    pixel_ratio: float = 1.0
    x_sampling: Optional[float] = None
    y_sampling: Optional[float] = None
    expand: bool = True
    target: Optional[Dataset] = None

    xunit: float = 0.0
    yunit: float = 0.0
    xs: Optional[np.ndarray] = None
    ys: Optional[np.ndarray] = None
    xtype: str = "numeric"
    ytype: str = "numeric"

    x_range_dt: Optional[Tuple[Any, Any]] = None
    y_range_dt: Optional[Tuple[Any, Any]] = None
    xs_dt: Optional[np.ndarray] = None
    ys_dt: Optional[np.ndarray] = None

    bounds: Optional[Tuple[float, float, float, float]] = None
    precomputed: dict = field(default_factory=dict)
    use_precompute: bool = False
    plot_id: Optional[Any] = None

    metadata: dict = field(default_factory=dict)

    @classmethod
    def create(cls, operation: Any, element: Any,
               x_dim: Optional[Any] = None, y_dim: Optional[Any] = None,
               ndim: int = 2, default: Optional[Tuple[float, float]] = None,
               use_cache: bool = True) -> "OperationExecutionContext":
        """Factory method to create and compute a complete execution context.

        Args:
            operation: The operation instance containing parameters
            element: The input element to process
            x_dim: x dimension(s), can be a single dimension or list
            y_dim: y dimension(s), can be a single dimension or list
            ndim: Number of dimensions (1 or 2)
            default: Default y_range if not specified
            use_cache: Whether to use operation's precomputed cache

        Returns:
            Fully populated OperationExecutionContext
        """
        p = operation.p
        ctx = cls(
            element=element,
            x_dim=x_dim,
            y_dim=y_dim,
            ndim=ndim,
            default_y_range=default,
            x_range=p.x_range if hasattr(p, 'x_range') else None,
            y_range=p.y_range if hasattr(p, 'y_range') else None,
            width=p.width if hasattr(p, 'width') else 400,
            height=p.height if hasattr(p, 'height') else 400,
            pixel_ratio=p.pixel_ratio if hasattr(p, 'pixel_ratio') else None,
            x_sampling=p.x_sampling if hasattr(p, 'x_sampling') else None,
            y_sampling=p.y_sampling if hasattr(p, 'y_sampling') else None,
            expand=p.expand if hasattr(p, 'expand') else True,
            target=p.target if hasattr(p, 'target') else None,
            use_precompute=p.precompute if hasattr(p, 'precompute') else False,
            precomputed=getattr(operation, '_precomputed', {}),
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

        return ctx

    def _compute_ranges(self) -> None:
        """Compute x_range and y_range from target, params, or element data."""
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
        """Determine dimension types (numeric vs datetime) and convert ranges."""
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
        """Adjust width and height based on pixel ratio."""
        if hasattr(self, 'operation'):
            pixel_ratio = self.operation._get_pixel_ratio()
        elif self.pixel_ratio is not None:
            pixel_ratio = self.pixel_ratio
        else:
            try:
                from panel import state
                if state.browser_info and isinstance(
                    state.browser_info.device_pixel_ratio, (int, float)
                ):
                    pixel_ratio = state.browser_info.device_pixel_ratio
                else:
                    pixel_ratio = 1
            except Exception:
                pixel_ratio = 1

        self.pixel_ratio = pixel_ratio
        self.width = int(self.width * pixel_ratio)
        self.height = int(self.height * pixel_ratio)

    def _apply_sampling_limits(self) -> None:
        """Apply x_sampling and y_sampling to limit width/height."""
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
        """Compute xunit, yunit and xs, ys coordinate arrays."""
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

        self.xs = np.linspace(
            xstart + self.xunit / 2.0, xend - self.xunit / 2.0, self.width
        ) if self.width > 0 else np.array([])

        self.ys = np.linspace(
            ystart + self.yunit / 2.0, yend - self.yunit / 2.0, self.height
        ) if self.height > 0 else np.array([])

    def _compute_bounds(self) -> None:
        """Compute the bounds tuple from ranges."""
        x0, x1 = self.x_range
        if self.ndim == 2 and self.y_range is not None:
            y0, y1 = self.y_range
        else:
            y0, y1 = 0, 0
        self.bounds = (x0, y0, x1, y1)

    def _transform_datetimes(self) -> None:
        """Transform integer datetime values back to datetime64 for output."""
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

    def get_sampling_result(self) -> Tuple[
        Tuple[Tuple[float, float], Tuple[float, float]],
        Tuple[np.ndarray, np.ndarray],
        Tuple[int, int],
        Tuple[str, str]
    ]:
        """Return the original _get_sampling tuple format for backward compatibility."""
        return (
            (self.x_range, self.y_range),
            (self.xs, self.ys),
            (self.width, self.height),
            (self.xtype, self.ytype),
        )

    def get_dt_transform_result(self) -> Tuple[
        Tuple[Tuple[Any, Any], Tuple[Any, Any]],
        Tuple[np.ndarray, np.ndarray]
    ]:
        """Return the original _dt_transform tuple format for backward compatibility."""
        return (
            (self.x_range_dt, self.y_range_dt),
            (self.xs_dt, self.ys_dt),
        )

    def is_empty(self) -> bool:
        """Check if the context represents an empty/zero-size grid."""
        return self.width == 0 or self.height == 0

    def cache_result(self, key: Any, value: Any) -> None:
        """Store a value in the precomputed cache if precomputing is enabled."""
        if self.use_precompute and self.plot_id is not None:
            self.precomputed[self.plot_id] = value

    def get_cached(self, key: Any) -> Optional[Any]:
        """Retrieve a value from the precomputed cache."""
        if self.plot_id is not None and self.plot_id in self.precomputed:
            return self.precomputed[self.plot_id]
        return None

    def has_cached(self, key: Any) -> bool:
        """Check if a key exists in the precomputed cache."""
        return self.plot_id is not None and self.plot_id in self.precomputed


class LinkableOperation(Operation):
    """Abstract baseclass for operations supporting linked inputs."""

    link_inputs = param.Boolean(
        default=True,
        doc="""
        By default, the link_inputs parameter is set to True so that
        when applying an operation, backends that support linked
        streams update RangeXY streams on the inputs of the operation.
        Disable when you do not want the resulting plot to be
        interactive, e.g. when trying to display an interactive plot a
        second time.""",
    )

    _allow_extra_keywords = True


class ResampleOperation1D(LinkableOperation):
    """Abstract baseclass for resampling operations"""

    dynamic = param.Boolean(
        default=True,
        doc="Enables dynamic processing by default.",
    )

    x_range = param.Tuple(
        default=None,
        length=2,
        doc="""
        The x_range as a tuple of min and max x-value. Auto-ranges
        if set to None.""",
    )

    x_sampling = param.Number(
        default=None,
        doc="Specifies the smallest allowed sampling interval along the x axis.",
    )

    streams = param.ClassSelector(
        default=[PlotSize, RangeX],
        class_=(dict, list),
        doc="""
        List or dictionary of streams that are applied if dynamic=True,
        allowing for dynamic interaction with the plot.""",
    )

    width = param.Integer(
        default=400,
        doc="The width of the output image in pixels.",
    )

    height = param.Integer(
        default=400,
        doc="The height of the output image in pixels.",
    )

    pixel_ratio = param.Number(
        default=None,
        bounds=(0, None),
        inclusive_bounds=(False, False),
        doc="""
        Pixel ratio applied to the height and width. Useful for higher
        resolution screens where the PlotSize stream reports 'nominal'
        dimensions in pixels that do not match the physical pixels. For
        instance, setting pixel_ratio=2 can give better results on Retina
        displays. Also useful for using lower resolution for speed.
        If not set explicitly, the zoom level of the browsers will be used,
        if available.""",
    )


class ResampleOperation2D(ResampleOperation1D):
    """Abstract baseclass for resampling operations"""

    dynamic = param.Boolean(
        default=True,
        doc="Enables dynamic processing by default.",
    )

    expand = param.Boolean(
        default=True,
        doc="""
        Whether the x_range and y_range should be allowed to expand
        beyond the extent of the data.  Setting this value to True is
        useful for the case where you want to ensure a certain size of
        output grid, e.g. if you are doing masking or other arithmetic
        on the grids.  A value of False ensures that the grid is only
        just as large as it needs to be to contain the data, which will
        be faster and use less memory if the resulting aggregate is
        being overlaid on a much larger background.""",
    )

    y_range = param.Tuple(
        default=None,
        length=2,
        doc="""
        The y-axis range as a tuple of min and max y value. Auto-ranges
        if set to None.""",
    )

    y_sampling = param.Number(
        default=None,
        doc="Specifies the smallest allowed sampling interval along the y axis.",
    )

    target = param.ClassSelector(
        class_=Dataset,
        doc="""
        A target Dataset which defines the desired x_range, y_range,
        width and height.""",
    )

    streams = param.ClassSelector(
        default=[PlotSize, RangeXY],
        class_=(dict, list),
        doc="""
        List or dictionary of streams that are applied if dynamic=True,
        allowing for dynamic interaction with the plot.""",
    )

    element_type = param.ClassSelector(
        class_=(Dataset,),
        instantiate=False,
        is_instance=False,
        default=Image,
        doc="The type of the returned Elements, must be a 2D Dataset type.",
    )

    precompute = param.Boolean(
        default=False,
        doc="""
        Whether to apply precomputing operations. Precomputing can
        speed up resampling operations by avoiding unnecessary
        recomputation if the supplied element does not change between
        calls. The cost of enabling this option is that the memory
        used to represent this internal state is not freed between
        calls.""",
    )

    _transfer_options = []

    @bothmethod
    def instance(self_or_cls, **params):
        filtered = {k: v for k, v in params.items() if k in self_or_cls.param}
        inst = super().instance(**filtered)
        inst._precomputed = {}
        return inst

    def _create_execution_context(self, element, x, y, ndim=2, default=None):
        """Create a unified OperationExecutionContext for this operation.

        This is the preferred method for new code. It consolidates all
        sampling parameters, range calculations, and pixel dimensions
        into a single context object that can be passed through the
        entire execution pipeline.

        Args:
            element: The input element to process
            x: x dimension(s)
            y: y dimension(s)
            ndim: Number of dimensions (1 or 2)
            default: Default y_range if not specified

        Returns:
            OperationExecutionContext with all computed values
        """
        return OperationExecutionContext.create(
            operation=self,
            element=element,
            x_dim=x,
            y_dim=y,
            ndim=ndim,
            default=default,
        )

    def _get_sampling(self, element, x, y, ndim=2, default=None):
        """Legacy method for backward compatibility.

        Prefer using _create_execution_context for new code.
        """
        ctx = self._create_execution_context(element, x, y, ndim, default)
        return ctx.get_sampling_result()

    def _get_pixel_ratio(self):
        if self.p.pixel_ratio is None:
            from panel import state

            if state.browser_info and isinstance(
                state.browser_info.device_pixel_ratio, (int, float)
            ):
                return state.browser_info.device_pixel_ratio
            else:
                return 1
        else:
            return self.p.pixel_ratio

    def _dt_transform(self, x_range=None, y_range=None, xs=None, ys=None,
                      xtype=None, ytype=None, ctx=None):
        """Transform datetime ranges and coordinates.

        Can be called with either individual parameters (legacy) or
        with an OperationExecutionContext (preferred).

        Args:
            x_range: x range tuple (legacy)
            y_range: y range tuple (legacy)
            xs: x coordinates array (legacy)
            ys: y coordinates array (legacy)
            xtype: x dimension type (legacy)
            ytype: y dimension type (legacy)
            ctx: OperationExecutionContext (preferred)

        Returns:
            Tuple of transformed ranges and coordinates
        """
        if ctx is not None:
            return ctx.get_dt_transform_result()

        (xstart, xend), (ystart, yend) = x_range, y_range
        if xtype == "datetime":
            xstart, xend = np.array([xstart, xend]).astype("datetime64[ns]")
            xs = xs.astype("datetime64[ns]")
        if ytype == "datetime":
            ystart, yend = np.array([ystart, yend]).astype("datetime64[ns]")
            ys = ys.astype("datetime64[ns]")
        return ((xstart, xend), (ystart, yend)), (xs, ys)


class ResampleOperationGuard(OperationGuard):
    """Operation guard specialized for resampling operations.

    Integrates with OperationExecutionContext for:
    - Context-aware empty checking (zero dimensions + empty data)
    - Context-aware caching via _precomputed and element._plot_id
    - Standardized exception wrapping with context info
    """

    _guard_enabled: bool = True
    _guard_record_time: bool = True
    _guard_wrap_exceptions: bool = True
    _guard_write_metadata: bool = False

    _guard_cache_params: list = [
        "width",
        "height",
        "x_range",
        "y_range",
        "pixel_ratio",
        "expand",
        "x_sampling",
        "y_sampling",
    ]

    def _normalize_params(self, element: Any, key: Any = None) -> Any:
        """Default parameter normalization for resampling operations."""
        return element

    def _check_empty(self, element: Any, key: Any = None) -> bool:
        """Check for empty conditions common to resampling ops.

        Checks both:
        1. Explicit __len__ == 0
        2. Context is_empty() (width == 0 or height == 0) if ctx is passed
        """
        if super()._check_empty(element, key):
            return True
        if isinstance(element, tuple) and len(element) >= 2:
            ctx = element[1] if isinstance(element[1], OperationExecutionContext) else None
            if ctx is not None and ctx.is_empty():
                return True
        return False

    def _get_cache_key(self, element: Any, key: Any = None) -> Any:
        """Extract cache key - prefers element._plot_id + dynamic params."""
        el = element[0] if isinstance(element, tuple) else element
        base_key = super()._get_cache_key(el, key)
        return base_key

    def _check_cache(self, element: Any, key: Any = None) -> Optional[Any]:
        """Check precomputed cache with plot_id."""
        cache_key = self._get_cache_key(element, key)
        precomputed = getattr(self, "_precomputed", {})
        if cache_key in precomputed:
            return precomputed[cache_key]
        return None

    def _update_cache(self, element: Any, key: Any = None, output: Any = None) -> None:
        """Update precomputed cache if precompute=True."""
        precompute = getattr(self.p, "precompute", False)
        if not precompute:
            return
        cache_key = self._get_cache_key(element, key)
        if not hasattr(self, "_precomputed"):
            self._precomputed = {}
        self._precomputed[cache_key] = output

    def _handle_exception(
        self,
        element: Any,
        key: Any,
        exception: Exception,
        guard_result: ExecutionGuardResult,
    ) -> Any:
        """Wrap exception with operation name and context."""
        el = element[0] if isinstance(element, tuple) else element
        op_name = type(self).__name__
        el_type = type(el).__name__
        raise type(exception)(
            f"Error in operation '{op_name}' processing {el_type}: {exception}"
        ).with_traceback(exception.__traceback__) from exception


class GuardedResampleOperation2D(ResampleOperationGuard, ResampleOperation2D):
    """Base class for 2D resampling operations with full guard protection.

    Subclasses should implement _process_core instead of _process.
    The guard pipeline automatically handles:
    - Parameter normalization via _normalize_params
    - Empty data short-circuit via _check_empty + _empty_result
    - Cache checking via _check_cache (uses _plot_id + _precomputed)
    - Exception wrapping via _handle_exception
    - Timing recording via _guard_record_time
    - Metadata writing via _write_metadata

    Example:
        class MyResample(GuardedResampleOperation2D):
            def _normalize_params(self, element, key=None, **kwargs):
                x, y = element.dimensions()[:2]
                ctx = self._create_execution_context(element, x, y)
                return element, ctx

            def _empty_result(self, normalized, key=None):
                element, ctx = normalized
                # return empty Image with correct bounds etc.
                ...

            def _process_core(self, normalized, key=None, **kwargs):
                element, ctx = normalized
                # core processing logic
                ...
    """

    def _process(self, element: Any, key: Any = None, **kwargs: Any) -> Any:
        """Override _process to wrap with execution guard."""
        return self._apply_guard(element, key, **kwargs)


class GuardedResampleOperation1D(ResampleOperationGuard, ResampleOperation1D):
    """Base class for 1D resampling operations with full guard protection.

    Subclasses should implement _process_core instead of _process.
    """

    def _process(self, element: Any, key: Any = None, **kwargs: Any) -> Any:
        """Override _process to wrap with execution guard."""
        return self._apply_guard(element, key, **kwargs)
