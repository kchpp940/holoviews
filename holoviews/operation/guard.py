"""Unified Operation Execution Guard.

Provides a reusable execution guard layer that consolidates:
- Parameter normalization
- Empty data short-circuit
- Cache hit detection
- Exception wrapping
- Execution time recording
- Output metadata writing back (attached to output objects via _guard_info)

Operations can inherit from GuardedOperationMixin and implement _process_core
instead of _process to automatically get all guard features.

For resampling operations, use GuardedResampleOperation2D which integrates
with the existing OperationExecutionContext pattern.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ..core import Operation


@dataclass
class ExecutionGuardResult:
    """Result from the execution guard, containing full metadata about the execution.

    An instance of this dataclass is attached to every output object
    produced by a guarded operation via the ``_guard_info`` attribute,
    so that metadata follows the product (not only the operation instance).

    Attributes:
        success:       Whether the execution completed (including empty short-circuit)
        cached:        Whether the result came from cache
        empty:         Whether the execution short-circuited on empty input
        error:         The exception object if an error occurred
        error_traceback: Full traceback string if an error occurred
        execution_time: Total wall-clock time for the guard pipeline (seconds)
        cache_time:    Time spent checking the cache (seconds)
        normalize_time: Time spent normalising params (seconds)
        normalized_params: Result of _normalize_params so downstream can inspect
        timestamp:     UTC timestamp of when the guard started
        metadata:      Free-form extra metadata dict
        output:        Reference to the produced output object
    """

    success: bool = True
    cached: bool = False
    empty: bool = False
    error: Optional[Exception] = None
    error_traceback: Optional[str] = None
    execution_time: float = 0.0
    cache_time: float = 0.0
    normalize_time: float = 0.0
    normalized_params: Any = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)
    output: Any = None

    def to_summary_dict(self) -> dict:
        """Return a plain-dict summary (e.g. for logging / debugging / tests).

        Does not include the ``output`` reference or exception objects.
        """
        d = {
            "success": self.success,
            "cached": self.cached,
            "empty": self.empty,
            "execution_time": self.execution_time,
            "cache_time": self.cache_time,
            "normalize_time": self.normalize_time,
            "timestamp": self.timestamp.isoformat(),
            "operation": self.metadata.get("operation"),
        }
        if self.error is not None:
            d["error"] = f"{type(self.error).__name__}: {self.error}"
        return d


class OperationGuard:
    """Core execution guard logic that can be mixed into any Operation.

    The guard wraps the core processing logic with a standard pipeline:
    1. _normalize_params - parameter validation and normalization
    2. _check_empty - short-circuit on empty input
    3. _check_cache - return cached result if available
    4. _process_core - actual operation logic (to be implemented by subclasses)
    5. _finalize_result - attach ExecutionGuardResult to output (recursive for composites)
    6. _update_cache - store result in cache

    Every produced object receives a ``_guard_info`` attribute holding the
    full ExecutionGuardResult so that metadata follows the product.
    """

    _guard_enabled: bool = True
    _guard_record_time: bool = True
    _guard_wrap_exceptions: bool = True
    _guard_write_metadata: bool = True

    _guard_cache_params: list = []

    # ------------------------------------------------------------------ utils
    def _get_cache_params(self) -> dict:
        """Get parameter values that should be included in cache key.

        Override _guard_cache_params or this method to specify which
        operation parameters affect the output and should invalidate
        the cache when they change.

        Supports both self.p (ParamOverrides, set during __call__)
        and direct param attributes on self.

        Returns:
            Dictionary of parameter names to values
        """
        params = {}
        for param_name in self._guard_cache_params:
            value = None
            found = False
            if hasattr(self, "p") and hasattr(self.p, param_name):
                value = getattr(self.p, param_name)
                found = True
            elif hasattr(self, "param") and param_name in self.param:
                value = getattr(self, param_name)
                found = True
            if found:
                params[param_name] = value
        return params

    # ------------------------------------------------------------ core pipeline
    def _apply_guard(
        self,
        element: Any,
        key: Any = None,
        process_fn: Optional[Callable] = None,
        **kwargs: Any,
    ) -> Any:
        """Apply the execution guard around a processing function.

        Args:
            element: The input element to process
            key: Optional key for the element
            process_fn: The core processing function. If None, uses self._process_core
            **kwargs: Additional keyword arguments passed to normalize/process hooks

        Returns:
            The processed output element, with ``_guard_info`` attached.
        """
        if not self._guard_enabled:
            if process_fn:
                return process_fn(element, key, **kwargs)
            return self._process_core(element, key, **kwargs)

        result = ExecutionGuardResult()
        result.metadata["operation"] = type(self).__name__

        try:
            t0 = time.perf_counter()

            normalized = self._normalize_params(element, key, **kwargs)
            result.normalize_time = time.perf_counter() - t0
            result.normalized_params = normalized

            if self._check_empty(normalized, key):
                result.empty = True
                output = self._empty_result(normalized, key)
                result.output = output
                result.execution_time = time.perf_counter() - t0
                self._last_guard_result = result
                return self._finalize_result(output, result)

            t1 = time.perf_counter()
            cached = self._check_cache(normalized, key)
            result.cache_time = time.perf_counter() - t1

            if cached is not None:
                result.cached = True
                output = self._clone_for_cache_hit(cached)
                result.output = output
                result.execution_time = time.perf_counter() - t0
                self._last_guard_result = result
                return self._finalize_result(output, result)

            t2 = time.perf_counter()
            if process_fn:
                output = process_fn(normalized, key, **kwargs)
            else:
                output = self._process_core(normalized, key, **kwargs)
            result.execution_time = time.perf_counter() - t0

            self._update_cache(normalized, key, output)

            result.output = output
            self._last_guard_result = result
            return self._finalize_result(output, result)

        except Exception as e:
            result.success = False
            result.error = e
            result.error_traceback = traceback.format_exc()
            result.execution_time = result.execution_time or (time.perf_counter() - t0 if "t0" in dir() else 0.0)

            self._last_guard_result = result

            if self._guard_wrap_exceptions:
                return self._handle_exception(element, key, e, result)
            else:
                raise

    # ------------------------------------------------------ per-stage override hooks
    def _normalize_params(self, element: Any, key: Any = None, **kwargs: Any) -> Any:
        """Normalize and validate input parameters.

        Override this method to perform parameter validation and normalization
        before the main processing logic.  The return value is saved as
        ``ExecutionGuardResult.normalized_params`` so downstream code can inspect
        the canonical parameter values that were actually used.

        Args:
            element: The input element
            key: Optional key
            **kwargs: Additional context arguments (e.g. shared_data)

        Returns:
            The normalized element (or a tuple/dict of normalized values)
        """
        return element

    def _check_empty(self, element: Any, key: Any = None) -> bool:
        """Check if the input is empty and should short-circuit."""
        # Overlay/NdMapping may raise NotImplementedError on .shape / __len__
        # so we aggressively catch all exceptions here.
        try:
            if hasattr(element, "shape"):
                try:
                    import numpy as _np
                    if _np.prod(element.shape) == 0:
                        return True
                except Exception:
                    pass
            if hasattr(element, "__len__"):
                try:
                    return len(element) == 0
                except Exception:
                    pass
        except Exception:
            return False
        return False

    def _empty_result(self, element: Any, key: Any = None) -> Any:
        """Generate an empty result for short-circuit cases."""
        if hasattr(element, "clone"):
            return element.clone([])
        return element

    def _get_cache_key(self, element: Any, key: Any = None) -> Any:
        """Compute a cache key for the input."""
        plot_id = getattr(element, "_plot_id", None)
        if plot_id is not None:
            base_key = plot_id
        else:
            base_key = id(element)

        cache_params = self._get_cache_params()
        if cache_params:
            return (base_key, tuple(sorted(cache_params.items())))
        return base_key

    def _check_cache(self, element: Any, key: Any = None) -> Optional[Any]:
        """Check if there's a cached result for this input."""
        cache_key = self._get_cache_key(element, key)
        precomputed = getattr(self, "_precomputed", {})
        if cache_key in precomputed:
            return precomputed[cache_key]
        return None

    def _update_cache(self, element: Any, key: Any = None, output: Any = None) -> None:
        """Store the result in cache."""
        precompute = getattr(self.p, "precompute", False) if hasattr(self, "p") else False
        if not precompute:
            return

        cache_key = self._get_cache_key(element, key)
        if not hasattr(self, "_precomputed"):
            self._precomputed = {}
        self._precomputed[cache_key] = output

    def _clone_for_cache_hit(self, cached: Any) -> Any:
        """Clone a cached result before returning it.

        When a cache hit occurs, the cached object already has ``_guard_info``
        from the original execution.  We must return a fresh copy so that the
        new call's guard info (``cached=True``, new timing, etc.) can be
        attached without mutating the original cached object (which may still
        be referenced by other callers).

        Falls back to returning the original object if cloning is not possible.
        """
        if cached is None:
            return cached
        if hasattr(cached, "clone"):
            try:
                return cached.clone()
            except Exception:
                pass
        return cached

    def _process_core(self, element: Any, key: Any = None, **kwargs: Any) -> Any:
        """Core processing logic - to be implemented by subclasses.

        This is the equivalent of the original _process method, but wrapped
        with all guard features.
        """
        raise NotImplementedError(
            "Subclasses must implement _process_core when using OperationGuard"
        )

    # -------------------------------------------------------- metadata / finalize
    def _attach_guard_info(self, obj: Any, guard_result: ExecutionGuardResult) -> Any:
        """Attach ``_guard_info`` to a single object, if possible.

        Tries (in order):
          1. Direct attribute assignment (``obj._guard_info = guard_result``)
          2. If obj exposes a dict-like ``attrs``, store under ``_guard_info`` key
          3. Clone with ``metadata=...`` for objects that support it
          4. Otherwise fall back to no-op (return original object)
        """
        try:
            obj._guard_info = guard_result
            return obj
        except Exception:
            pass

        try:
            if hasattr(obj, "attrs") and isinstance(obj.attrs, dict):
                obj.attrs["_guard_info"] = guard_result
                return obj
        except Exception:
            pass

        try:
            if hasattr(obj, "clone"):
                summary = guard_result.to_summary_dict()
                existing_meta = getattr(obj, "metadata", {}) or {}
                new_meta = dict(existing_meta)
                new_meta.setdefault("_guard_info_summary", summary)
                return obj.clone(metadata=new_meta)
        except Exception:
            pass

        return obj

    def _is_composite(self, obj: Any) -> bool:
        """Return True if *obj* is a container whose leaf children should also
        receive ``_guard_info``.

        Covers HoloViews Overlay, NdOverlay, Layout, NdLayout, HoloMap,
        GridSpace and any generic object implementing ``.traverse()``.
        """
        # Composite containers are "deep indexable" in HoloViews terminology.
        from ..core.util import _is_deep_indexable

        if _is_deep_indexable(obj):
            return True
        # Fall back to a quick structural check
        if hasattr(obj, "traverse") and hasattr(obj, "map"):
            return True
        return False

    def _write_metadata(self, output: Any, guard_result: ExecutionGuardResult) -> Any:
        """Write execution metadata to the output element (legacy hook).

        The primary metadata attachment is now performed by ``_finalize_result``
        via ``_attach_guard_info``.  This hook is kept for backwards
        compatibility; any transformations it performs are applied *after*
        ``_attach_guard_info``.
        """
        if not self._guard_write_metadata:
            return output

        # Build a quick summary for attrs/metadata slots if user code looks there.
        summary = guard_result.to_summary_dict()

        if hasattr(output, "attrs") and isinstance(output.attrs, dict):
            output.attrs.setdefault("_guard_metadata", summary)

        if hasattr(output, "clone"):
            try:
                existing_meta = getattr(output, "metadata", {}) or {}
                if isinstance(existing_meta, dict):
                    existing_meta.setdefault("_guard_summary", summary)
            except Exception:
                pass

        return output

    def _finalize_result(self, output: Any, guard_result: ExecutionGuardResult) -> Any:
        """Finalize the result: attach guard info to the output recursively.

        For composite containers (Overlay / NdOverlay / HoloMap / Layout / ...)
        we both:
          * attach the guard info to the container itself, AND
          * traverse into every leaf child and attach the guard info there,
            so downstream code that unpacks the container still gets the
            execution metadata on every individual element.

        Args:
            output:        The processed output (element or composite)
            guard_result:  The :class:`ExecutionGuardResult` to attach

        Returns:
            The finalized output element (possibly same object, possibly cloned)
        """
        if output is None:
            return output

        # 1. attach guard info to the top-level object
        output = self._attach_guard_info(output, guard_result)

        # 2. for composite containers, recurse into every leaf child
        if self._is_composite(output):
            try:
                output = output.map(
                    lambda leaf: self._attach_guard_info(leaf, guard_result)
                )
            except Exception:
                # traverse() fallback: in-place assignment is best-effort
                try:
                    for leaf in output.traverse():
                        self._attach_guard_info(leaf, guard_result)
                except Exception:
                    pass

        # 3. legacy backwards-compat hook
        try:
            output = self._write_metadata(output, guard_result)
        except Exception:
            pass

        return output

    # ------------------------------------------------------------- error handling
    def _handle_exception(
        self,
        element: Any,
        key: Any,
        exception: Exception,
        guard_result: ExecutionGuardResult,
    ) -> Any:
        """Handle exceptions during execution.

        Override this method to customize exception handling.
        By default, re-raises the exception with additional context.
        """
        op_name = type(self).__name__
        raise type(exception)(
            f"Error in operation '{op_name}': {exception}"
        ).with_traceback(exception.__traceback__) from exception


class GuardedOperationMixin(OperationGuard):
    """Mixin that makes an Operation use the execution guard.

    Usage::

        class MyOperation(GuardedOperationMixin, Operation):
            def _process_core(self, element, key=None, **kwargs):
                # Core logic here
                return result

    Or with existing base classes::

        class MyOperation(GuardedOperationMixin, ResampleOperation2D):
            def _process_core(self, element, key=None, **kwargs):
                # Core logic here
                return result
    """

    def _process(self, element: Any, key: Any = None, **kwargs: Any) -> Any:
        """Override _process to wrap with execution guard."""
        return self._apply_guard(element, key, **kwargs)
