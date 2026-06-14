"""Unified Operation Execution Guard.

Provides a reusable execution guard layer that consolidates:
- Parameter normalization
- Empty data short-circuit
- Cache hit detection
- Exception wrapping
- Execution time recording
- Output metadata writing back

Operations can inherit from GuardedOperationMixin and implement _process_core
instead of _process to automatically get all guard features.

For resampling operations, use GuardedResampleOperation2D which integrates
with the existing OperationExecutionContext pattern.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..core import Operation


@dataclass
class ExecutionGuardResult:
    """Result from the execution guard, containing metadata about the execution."""

    success: bool = True
    cached: bool = False
    empty: bool = False
    error: Optional[Exception] = None
    error_traceback: Optional[str] = None
    execution_time: float = 0.0
    cache_time: float = 0.0
    normalize_time: float = 0.0
    metadata: dict = field(default_factory=dict)
    output: Any = None


class OperationGuard:
    """Core execution guard logic that can be mixed into any Operation.

    The guard wraps the core processing logic with a standard pipeline:
    1. _normalize_params - parameter validation and normalization
    2. _check_empty - short-circuit on empty input
    3. _check_cache - return cached result if available
    4. _process_core - actual operation logic (to be implemented by subclasses)
    5. _write_metadata - attach execution metadata to output
    6. _update_cache - store result in cache
    """

    _guard_enabled: bool = True
    _guard_record_time: bool = True
    _guard_wrap_exceptions: bool = True
    _guard_write_metadata: bool = False

    def _apply_guard(
        self,
        element: Any,
        key: Any = None,
        process_fn: Optional[Callable] = None,
    ) -> Any:
        """Apply the execution guard around a processing function.

        Args:
            element: The input element to process
            key: Optional key for the element
            process_fn: The core processing function. If None, uses self._process_core

        Returns:
            The processed output element
        """
        if not self._guard_enabled:
            if process_fn:
                return process_fn(element, key)
            return self._process_core(element, key)

        result = ExecutionGuardResult()

        try:
            t0 = time.perf_counter()

            normalized = self._normalize_params(element, key)
            result.normalize_time = time.perf_counter() - t0

            if self._check_empty(normalized, key):
                result.empty = True
                output = self._empty_result(normalized, key)
                result.output = output
                result.execution_time = time.perf_counter() - t0
                return self._finalize_result(output, result)

            t1 = time.perf_counter()
            cached = self._check_cache(normalized, key)
            result.cache_time = time.perf_counter() - t1

            if cached is not None:
                result.cached = True
                result.output = cached
                result.execution_time = time.perf_counter() - t0
                return self._finalize_result(cached, result)

            t2 = time.perf_counter()
            if process_fn:
                output = process_fn(normalized, key)
            else:
                output = self._process_core(normalized, key)
            result.execution_time = time.perf_counter() - t0

            self._update_cache(normalized, key, output)

            result.output = output
            return self._finalize_result(output, result)

        except Exception as e:
            result.success = False
            result.error = e
            result.error_traceback = traceback.format_exc()
            result.execution_time = result.execution_time or (time.perf_counter() - t0 if 't0' in dir() else 0.0)

            if self._guard_wrap_exceptions:
                return self._handle_exception(element, key, e, result)
            else:
                raise

    def _normalize_params(self, element: Any, key: Any = None) -> Any:
        """Normalize and validate input parameters.

        Override this method to perform parameter validation and normalization
        before the main processing logic.

        Args:
            element: The input element
            key: Optional key

        Returns:
            The normalized element (or a tuple of normalized values)
        """
        return element

    def _check_empty(self, element: Any, key: Any = None) -> bool:
        """Check if the input is empty and should short-circuit.

        Override this method to define empty conditions for your operation.

        Args:
            element: The (normalized) input element
            key: Optional key

        Returns:
            True if the input is empty and should short-circuit
        """
        if hasattr(element, "__len__"):
            try:
                return len(element) == 0
            except Exception:
                pass
        return False

    def _empty_result(self, element: Any, key: Any = None) -> Any:
        """Generate an empty result for short-circuit cases.

        Override this method to define what an empty result looks like.

        Args:
            element: The (normalized) input element
            key: Optional key

        Returns:
            An empty output element
        """
        if hasattr(element, "clone"):
            return element.clone([])
        return element

    def _get_cache_key(self, element: Any, key: Any = None) -> Any:
        """Compute a cache key for the input.

        Override this method to define cache keys for your operation.

        Args:
            element: The (normalized) input element
            key: Optional key

        Returns:
            A hashable cache key
        """
        plot_id = getattr(element, "_plot_id", None)
        if plot_id is not None:
            return plot_id
        return id(element)

    def _check_cache(self, element: Any, key: Any = None) -> Optional[Any]:
        """Check if there's a cached result for this input.

        Override this method to implement cache lookups.

        Args:
            element: The (normalized) input element
            key: Optional key

        Returns:
            The cached result if available, else None
        """
        cache_key = self._get_cache_key(element, key)
        precomputed = getattr(self, "_precomputed", {})
        if cache_key in precomputed:
            return precomputed[cache_key]
        return None

    def _update_cache(self, element: Any, key: Any = None, output: Any = None) -> None:
        """Store the result in cache.

        Override this method to implement cache storage.

        Args:
            element: The (normalized) input element
            key: Optional key
            output: The processed output
        """
        precompute = getattr(self.p, "precompute", False) if hasattr(self, "p") else False
        if not precompute:
            return

        cache_key = self._get_cache_key(element, key)
        if not hasattr(self, "_precomputed"):
            self._precomputed = {}
        self._precomputed[cache_key] = output

    def _process_core(self, element: Any, key: Any = None) -> Any:
        """Core processing logic - to be implemented by subclasses.

        This is the equivalent of the original _process method, but wrapped
        with all guard features.

        Args:
            element: The (normalized) input element
            key: Optional key

        Returns:
            The processed output element
        """
        raise NotImplementedError(
            "Subclasses must implement _process_core when using OperationGuard"
        )

    def _write_metadata(self, output: Any, guard_result: ExecutionGuardResult) -> Any:
        """Write execution metadata to the output element.

        Override this method to attach custom metadata.

        Args:
            output: The processed output element
            guard_result: The guard result with execution metadata

        Returns:
            The output element with metadata attached
        """
        if not self._guard_write_metadata:
            return output

        metadata = {
            "operation": type(self).__name__,
            "cached": guard_result.cached,
            "empty": guard_result.empty,
            "success": guard_result.success,
        }

        if self._guard_record_time:
            metadata["execution_time"] = guard_result.execution_time
            metadata["cache_time"] = guard_result.cache_time
            metadata["normalize_time"] = guard_result.normalize_time

        if hasattr(output, "attrs") and isinstance(output.attrs, dict):
            output.attrs["_guard_metadata"] = metadata
        elif hasattr(output, "clone"):
            try:
                existing_meta = getattr(output, "metadata", {}) or {}
                new_meta = {**existing_meta, **metadata}
                return output.clone(metadata=new_meta)
            except Exception:
                pass

        return output

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

        Args:
            element: The input element
            key: Optional key
            exception: The caught exception
            guard_result: The guard result with error info

        Raises:
            The original exception with added context
        """
        op_name = type(self).__name__
        raise type(exception)(
            f"Error in operation '{op_name}': {exception}"
        ).with_traceback(exception.__traceback__) from exception

    def _finalize_result(self, output: Any, guard_result: ExecutionGuardResult) -> Any:
        """Finalize the result by writing metadata.

        Args:
            output: The processed output element
            guard_result: The guard result with execution metadata

        Returns:
            The finalized output element
        """
        return self._write_metadata(output, guard_result)


class GuardedOperationMixin(OperationGuard):
    """Mixin that makes an Operation use the execution guard.

    Usage:
        class MyOperation(GuardedOperationMixin, Operation):
            def _process_core(self, element, key=None):
                # Core logic here
                return result

    Or with existing base classes:
        class MyOperation(GuardedOperationMixin, ResampleOperation2D):
            def _process_core(self, element, key=None):
                # Core logic here
                return result
    """

    def _process(self, element: Any, key: Any = None) -> Any:
        """Override _process to wrap with execution guard."""
        return self._apply_guard(element, key)
