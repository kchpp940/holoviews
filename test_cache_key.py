"""Test cache key generation with dynamic parameters."""
import numpy as np
import holoviews as hv
from holoviews.operation.downsample import downsample1d
from holoviews.operation.guard import OperationGuard
from holoviews.operation.resample import GuardedResampleOperation1D

hv.extension('bokeh')

print("=" * 70)
print("TEST 1: Cache key includes dynamic parameters")
print("=" * 70)

x = np.linspace(0, 10, 500)
y = np.cos(x)
curve = hv.Curve((x, y))

class TestOp(GuardedResampleOperation1D):
    def _process_core(self, element, key=None, **kwargs):
        return element

# Test with .instance()
op1 = TestOp.instance(width=200)
print(f"\n  op1.width = {op1.width}")
print(f"  op1.param names: {[p for p in op1.param if p in ['width', 'height', 'x_range']]}")
params1 = op1._get_cache_params()
print(f"  _get_cache_params() = {params1}")
key1 = op1._get_cache_key(curve)
print(f"  cache key = {key1}")

op2 = TestOp.instance(width=300)
print(f"\n  op2.width = {op2.width}")
params2 = op2._get_cache_params()
print(f"  _get_cache_params() = {params2}")
key2 = op2._get_cache_key(curve)
print(f"  cache key = {key2}")

print(f"\n  Keys differ (width 200 vs 300): {key1 != key2}")

# Test with x_range
op3 = TestOp.instance(width=200, x_range=(0, 5))
print(f"\n  op3.x_range = {op3.x_range}")
params3 = op3._get_cache_params()
print(f"  _get_cache_params() = {params3}")
key3 = op3._get_cache_key(curve)
print(f"  cache key = {key3}")
print(f"  Keys differ (with vs without x_range): {key1 != key3}")

# Same params should produce same key
op4 = TestOp.instance(width=200)
key4 = op4._get_cache_key(curve)
print(f"\n  Same params produce same key: {key1 == key4}")

print("\n" + "=" * 70)
print("TEST 2: Verify guard is called in dynamic=True path")
print("=" * 70)

guard_calls = []
original_apply_guard = OperationGuard._apply_guard

def traced_apply_guard(self, element, key=None, process_fn=None, **kwargs):
    result = original_apply_guard(self, element, key, process_fn, **kwargs)
    guard_calls.append({
        'op': type(self).__name__,
        'cache_params': self._get_cache_params(),
        'cache_key': self._get_cache_key(element, key),
    })
    return result

OperationGuard._apply_guard = traced_apply_guard

try:
    x = np.linspace(0, 10, 1000)
    y = np.sin(x)
    curve = hv.Curve((x, y), 'x', 'y')
    
    result = downsample1d(curve, width=100, dynamic=True)
    print(f"\n  Before evaluation: guard calls = {len(guard_calls)}")
    
    evaluated = result[()]
    print(f"  After evaluation: guard calls = {len(guard_calls)}")
    
    if guard_calls:
        call = guard_calls[-1]
        print(f"\n  Guard call details:")
        print(f"    Operation: {call['op']}")
        print(f"    Cache params: {call['cache_params']}")
        print(f"    Cache key includes params: {isinstance(call['cache_key'], tuple) and len(call['cache_key']) == 2}")

finally:
    OperationGuard._apply_guard = original_apply_guard

print("\n" + "=" * 70)
print("TEST 3: Exception wrapping on dynamic path")
print("=" * 70)

class TestErrorOp(GuardedResampleOperation1D):
    _guard_wrap_exceptions = True
    
    def _process_core(self, element, key=None, **kwargs):
        raise ValueError("test error from core")

x = np.linspace(0, 10, 100)
y = np.sin(x)
curve = hv.Curve((x, y))

op = TestErrorOp.instance(width=50)
result = op(curve, dynamic=True)

print(f"\n  Evaluating DynamicMap with failing operation...")
try:
    evaluated = result[()]
    print(f"  ❌ No exception raised")
except Exception as e:
    print(f"  ✅ Exception type: {type(e).__name__}")
    print(f"  ✅ Exception message contains op name: {'TestErrorOp' in str(e)}")
    print(f"     Message: {e}")

print("\n" + "=" * 70)
print("Summary")
print("=" * 70)
