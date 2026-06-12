"""Unified accessors for operation execution context metadata.

This module provides a single public entry point —
:func:`get_execution_context_meta` — that surfaces the runtime metadata
attached to objects produced by rasterize / datashade / resample and
other operations.

Display-layer code (e.g. the ``OperationContextExtension`` in
``core.display_extension``) should *only* consume the metadata via this
module, never inspect ``_hv_execution_context`` or
``_operation_context`` directly.  This keeps the data format stable as
execution-context internals evolve.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


__all__ = [
    "get_execution_context_meta",
]


def get_execution_context_meta(obj: Any) -> Dict[str, Any]:
    """Extract a flat metadata dict describing the operation execution
    context that produced *obj*.

    The function tries several sources in priority order and merges
    the results (first-wins for any given key):

    1. ``obj._hv_execution_context`` — an
       :class:`~holoviews.operation.resample.OperationExecutionContext`
       instance attached by the operation itself.  ``to_metadata_dict()``
       is called on it if available.
    2. ``obj._operation_context`` — a generic dictionary that
       operations populate during ``_process`` with timing, parameter
       snapshots, provenance, etc.  Recognised sub-keys include
       ``sampling_meta``, ``bounds``, ``precompute``, ``elapsed_ms``,
       ``operation``.
    3. ``obj.callback.operation`` — when *obj* is a DynamicMap built
       by ``.apply()`` / ``.map()``, the underlying
       :class:`~holoviews.core.operation.Operation` is surfaced here.

    Parameters
    ----------
    obj:
        Any HoloViews object (Element, DynamicMap, Layout, ...).

    Returns
    -------
    dict
        Flat string-keyed metadata dictionary.  Empty when no execution
        context is associated with *obj*.
    """
    meta: Dict[str, Any] = {}

    _collect_from_hv_ctx(obj, meta)
    _collect_from_op_ctx(obj, meta)
    _collect_from_callback(obj, meta)

    return meta


def _collect_from_hv_ctx(obj: Any, meta: Dict[str, Any]) -> None:
    hv_ctx = getattr(obj, "_hv_execution_context", None)
    if hv_ctx is None:
        return
    try:
        scalar_attrs = (
            "width", "height", "pixel_ratio",
            "x_sampling", "y_sampling",
            "expand", "ndim", "xtype", "ytype",
            "use_precompute",
        )
        for attr in scalar_attrs:
            val = getattr(hv_ctx, attr, None)
            if val is not None:
                meta.setdefault(attr, val)

        x_range = getattr(hv_ctx, "x_range", None)
        if x_range is not None:
            meta.setdefault("x_range", tuple(x_range))
        y_range = getattr(hv_ctx, "y_range", None)
        if y_range is not None:
            meta.setdefault("y_range", tuple(y_range))
        bounds = getattr(hv_ctx, "bounds", None)
        if bounds is not None:
            meta.setdefault("bounds", tuple(bounds))

        xunit = getattr(hv_ctx, "xunit", None)
        if xunit:
            meta.setdefault("x_unit", xunit)
        yunit = getattr(hv_ctx, "yunit", None)
        if yunit:
            meta.setdefault("y_unit", yunit)

        x_dim = getattr(hv_ctx, "x_dim", None)
        if x_dim is not None:
            meta.setdefault("x_dim", str(x_dim))
        y_dim = getattr(hv_ctx, "y_dim", None)
        if y_dim is not None:
            meta.setdefault("y_dim", str(y_dim))

        precomputed = getattr(hv_ctx, "precomputed", None)
        plot_id = getattr(hv_ctx, "plot_id", None)
        if precomputed and plot_id is not None and plot_id in precomputed:
            meta.setdefault("precomputed_keys", [plot_id])

        metadata = getattr(hv_ctx, "metadata", None)
        if isinstance(metadata, dict):
            for k, v in metadata.items():
                meta.setdefault(k, v)
    except Exception:  # noqa: BLE001
        pass


def _collect_from_op_ctx(obj: Any, meta: Dict[str, Any]) -> None:
    op_ctx = getattr(obj, "_operation_context", None)
    if not op_ctx or not isinstance(op_ctx, dict):
        return

    sampling_meta = op_ctx.get("sampling_meta")
    if isinstance(sampling_meta, dict):
        for k, v in sampling_meta.items():
            meta.setdefault(k, v)

    for key in ("bounds", "precompute", "elapsed_ms", "operation",
                "operation_type", "operation_params", "pipeline_depth"):
        if key in op_ctx and op_ctx[key] is not None:
            meta.setdefault(key, op_ctx[key])


def _collect_from_callback(obj: Any, meta: Dict[str, Any]) -> None:
    callback = getattr(obj, "callback", None)
    if callback is None:
        return
    op = getattr(callback, "operation", None)
    if op is None:
        return
    meta.setdefault("operation", getattr(op, "__name__", type(op).__name__))
    meta.setdefault("operation_type", type(op).__name__)
    try:
        from . import Operation  # local import to avoid circular
        if isinstance(op, Operation):
            op_vals = {
                k: v for k, v in op.param.values().items()
                if k not in ("name",)
            }
            if op_vals:
                meta.setdefault("operation_params", op_vals)
    except Exception:  # noqa: BLE001
        pass
