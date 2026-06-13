"""Comprehensive validation of guard on both dynamic=True and dynamic=False paths."""
import numpy as np
import holoviews as hv
from holoviews.operation.downsample import downsample1d
from holoviews.operation.guard import OperationGuard, ExecutionGuardResult
from holoviews.operation.resample import GuardedResampleOperation1D, ResampleOperationGuard

hv.extension('bokeh')

passed = 0
failed = 0

def test(name, condition):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}")
        failed += 1

print("=" * 70)
print("Test Suite: Guard coverage on dynamic=True path")
print("=" * 70)

# Test data
x = np.linspace(0, 10, 1000)
y = np.sin(x)
curve = hv.Curve((x, y), 'x', 'y')

print("\n--- Test Group 1: Basic guard invocation (dynamic=True)")
print("-" * 40)

result = downsample1d(curve, width=100, dynamic=True)
test("Returns DynamicMap", isinstance(result, hv.DynamicMap))

evaluated = result[()]
test("Evaluated is Curve", isinstance(evaluated, hv.Curve))
test("Result is downsampled", len(evaluated) <= 100)
test("Result has correct dims", evaluated.kdims == curve.kdims)

print(f"\n--- Test Group 2: Basic guard invocation (dynamic=False)")
print("-" * 40)

result_static = downsample1d(curve, width=100, dynamic=False)
test("Returns Curve directly", isinstance(result_static, hv.Curve))
test("Result is downsampled", len(result_static) <= 100)
test("Dynamic and static results match length", len(evaluated) == len(result_static))

print(f"\n--- Test Group 3: Guard is actually called")
print("-" * 40)

guard_calls = []
original_apply_guard = OperationGuard._apply_guard

def traced_apply_guard(self, element, key=None, process_fn=None, **kwargs):
    guard_calls.append(type(self).__name__)
    return original_apply_guard(self, element, key, process_fn, **kwargs)

OperationGuard._apply_guard = traced_apply_guard

try:
    dynamic_result = downsample1d(curve, width=50, dynamic=True)
    test("Guard not called before evaluation", len(guard_calls) == 0)
    
    evaluated = dynamic_result[()]
    test("Guard called after evaluation", len(guard_calls) == 1)
    test("Guard called on downsample1d", guard_calls[0] == 'downsample1d')
    
    guard_calls.clear()
    
    static_result = downsample1d(curve, width=50, dynamic=False)
    test("Guard called on static path", len(guard_calls) == 1)

finally:
    OperationGuard._apply_guard = original_apply_guard

print(f"\n--- Test Group 4: Cache key includes dynamic parameters")
print("-" * 40)

op = downsample1d.instance(width=200)
key1 = op._get_cache_key(curve)

op2 = downsample1d.instance(width=300)
key2 = op2._get_cache_key(curve)

test("Different width → different cache keys", key1 != key2)

op3 = downsample1d.instance(width=200, x_range=(0, 5))
key3 = op3._get_cache_key(curve)

test("Different x_range → different cache keys", key1 != key3)

op4 = downsample1d.instance(width=200)
key4 = op4._get_cache_key(curve)

test("Same params → same cache key", key1 == key4)

cache_params = op._get_cache_params()
test("Cache params include width", 'width' in cache_params)
test("Cache params include height", 'height' in cache_params)
test("Cache params include x_range", 'x_range' in cache_params)

print(f"\n--- Test Group 5: _last_guard_result records execution metadata")
print("-" * 40)

class TestMetaOp(GuardedResampleOperation1D):
    _guard_write_metadata = False
    
    def _process_core(self, element, key=None, **kwargs):
        return element.clone(element.data.iloc[::2] if hasattr(element.data, 'iloc') else element.data)

test_op = TestMetaOp.instance(width=100)
result = test_op(curve, dynamic=False)
test("_last_guard_result exists", hasattr(test_op, '_last_guard_result'))
test("_last_guard_result is ExecutionGuardResult", isinstance(test_op._last_guard_result, ExecutionGuardResult))
test("_last_guard_result.success is True", test_op._last_guard_result.success)
test("_last_guard_result.cached is False", not test_op._last_guard_result.cached)
test("_last_guard_result.empty is False", not test_op._last_guard_result.empty)
test("_last_guard_result.execution_time > 0", test_op._last_guard_result.execution_time > 0)
test("_last_guard_result.output is set", test_op._last_guard_result.output is not None)

print(f"\n--- Test Group 6: Empty data short-circuit")
print("-" * 40)

empty_curve = hv.Curve([], 'x', 'y')
empty_result = downsample1d(empty_curve, width=50, dynamic=False)
test("Empty input returns empty output", len(empty_result) == 0)

print(f"\n--- Test Group 7: Exception wrapping")
print("-" * 40)

class TestErrorOp(GuardedResampleOperation1D):
    _guard_wrap_exceptions = True
    
    def _process_core(self, element, key=None, **kwargs):
        raise ValueError("test error")

err_op = TestErrorOp.instance(width=50)
try:
    err_op(curve, dynamic=False)
    test("Exception raised", False)
except ValueError as e:
    test("Exception is ValueError", isinstance(e, ValueError))
    test("Exception contains op name", 'TestErrorOp' in str(e))

# Test on dynamic path
err_result = err_op(curve, dynamic=True)
try:
    err_result[()]
    test("Dynamic path exception raised", False)
except ValueError as e:
    test("Dynamic path exception wrapped", 'TestErrorOp' in str(e))

print(f"\n--- Test Group 8: Guard can be disabled")
print("-" * 40)

class TestDisabledOp(GuardedResampleOperation1D):
    _guard_enabled = False
    
    def _process_core(self, element, key=None, **kwargs):
        return element

disabled_op = TestDisabledOp.instance(width=50)
disabled_result = disabled_op(curve, dynamic=False)
test("Disabled guard still works", len(disabled_result) == len(curve))
test("Disabled guard has no _last_guard_result", not hasattr(disabled_op, '_last_guard_result'))

print(f"\n--- Test Group 9: GuardedOperationMixin works")
print("-" * 40)

from holoviews.operation.guard import GuardedOperationMixin
from holoviews.core.operation import Operation

class TestMixinOp(GuardedOperationMixin, Operation):
    def _process_core(self, element, key=None, **kwargs):
        return element

mixin_op = TestMixinOp.instance()
mixin_result = mixin_op(curve, dynamic=False)
test("Mixin operation works", len(mixin_result) == len(curve))
test("Mixin operation has guard result", hasattr(mixin_op, '_last_guard_result'))

print("\n" + "=" * 70)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 70)

if failed > 0:
    exit(1)
