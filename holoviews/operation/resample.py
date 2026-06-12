from __future__ import annotations

import numpy as np
import param
from param.parameterized import bothmethod

from ..core import Dataset, Operation
from ..element import Image
from ..streams import PlotSize, RangeX, RangeXY
from .context import OperationExecutionContext


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
    """Abstract baseclass for resampling operations

    Provides ``_create_execution_context``, ``_get_sampling``,
    ``_get_pixel_ratio`` and ``_dt_transform`` helpers.  New callers
    should use ``_create_execution_context`` and work with the
    returned ``OperationExecutionContext`` directly.
    """

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

    # ------------------------------------------------------------------
    # Context creation (neutral entry point — shared with datashader)
    # ------------------------------------------------------------------
    def _create_execution_context(self, element, x, y, ndim=2, default=None):
        """Create a unified OperationExecutionContext for this operation.

        This is the preferred entry point for new code: it builds the
        complete execution context (ranges, pixel dimensions, sampling
        limits, unit/coordinate arrays, bounds, datetime transforms,
        sampling metadata, cache linkage) in one place.

        Parameters
        ----------
        element : Element
            The input element to process.
        x : Dimension or list of Dimension
            x dimension(s).
        y : Dimension or list of Dimension
            y dimension(s).
        ndim : {1, 2}
            Dimensionality of the rasterization.
        default : tuple, optional
            Default y-range fallback.

        Returns
        -------
        OperationExecutionContext
            Fully populated context from ``operation/context.py``.
        """
        return OperationExecutionContext.create(
            operation=self,
            element=element,
            x_dim=x,
            y_dim=y,
            ndim=ndim,
            default=default,
        )

    # ------------------------------------------------------------------
    # Backward-compat wrappers (thin shims over the context)
    # ------------------------------------------------------------------
    def _get_sampling(self, element, x, y, ndim=2, default=None):
        """Legacy method — returns the 4-tuple previously produced here.

        Prefer :meth:`_create_execution_context` for new code.
        """
        ctx = self._create_execution_context(element, x, y, ndim, default)
        return ctx.get_sampling_result()

    def _get_pixel_ratio(self):
        """Resolve the effective pixel_ratio.

        Delegates to the neutral helper in ``operation/context.py`` via
        the context's ``_apply_pixel_ratio`` stage.  Kept on the
        operation as a public shim for external callers.
        """
        pixel_ratio = (
            getattr(self.p, 'pixel_ratio', None)
            if hasattr(self, 'p')
            else getattr(self, 'pixel_ratio', None)
        )
        if pixel_ratio is None:
            try:
                from panel import state

                if state.browser_info and isinstance(
                    state.browser_info.device_pixel_ratio, (int, float)
                ):
                    return state.browser_info.device_pixel_ratio
                else:
                    return 1
            except Exception:
                return 1
        else:
            return pixel_ratio

    def _dt_transform(self, x_range=None, y_range=None, xs=None, ys=None,
                      xtype=None, ytype=None, ctx=None):
        """Transform datetime ranges and coordinates.

        Two call conventions:

        * **New (preferred):** pass ``ctx=OperationExecutionContext``
          — the context's cached ``get_dt_transform_result()`` is used
          directly, so duplicate work is avoided.
        * **Legacy:** pass the 6 individual parameters as before.
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


__all__ = [
    "LinkableOperation",
    "OperationExecutionContext",
    "ResampleOperation1D",
    "ResampleOperation2D",
]
