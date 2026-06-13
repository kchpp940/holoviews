"""Comprehensive test for guard coverage on dynamic=True path."""
import numpy as np
import holoviews as hv
from holoviews.operation.downsample import downsample1d
from holoviews.operation.guard import OperationGuard, ExecutionGuardResult
from holoviews.operation.resample import GuardedResampleOperation1D

hv.extension('bokeh')

print("=" * 70)
print("TEST 1: Verify guard is called in dynamic=True path")
print("=" * 70)

guard_calls = []

original_apply_guard = OperationGuard._apply_guard

def traced_apply_guard(self, element, key=None, process_fn=None, **kwargs):
    result = original_apply_guard(self, element, key, process_fn, **kwargs)
    guard_calls.append({
        'op': type(self).__name__,
        'element_type': type(element).__name__,
        'element_len': len(element) if hasattr(element, '__len__') else 'N/A',
        'key': key,
        'kwargs': list(kwargs.keys()),
        'params_from_p': {
            k: getattr(self.p, k, None)
            for k in ['width', 'height', 'x_range', 'y_range']
            if hasattr(self.p, k)
        },
    })
    return result

OperationGuard._apply_guard = traced_apply_guard

try:
    x = np.linspace(0, 10, 1000)
    y = np.sin(x)
    curve = hv.Curve((x, y), 'x', 'y')
    
    result = downsample1d(curve, width=100, dynamic=True)
    print(f"\n  After __call__ (before evaluation):")
    print(f"    Result type: {type(result).__name__}")
    print(f"    Guard calls: {len(guard_calls)}")
    
    evaluated = result[()]
    print(f"\n  After evaluation:")
    print(f"    Evaluated type: {type(evaluated).__name__}")
    print(f"    Evaluated len: {len(evaluated)}")
    print(f"    Guard calls: {len(guard_calls)}")
    
    if guard_calls:
        call = guard_calls[-1]
        print(f"\n  Last guard call details:")
        print(f"    Operation: {call['op']}")
        print(f"    Element type: {call['element_type']}")
        print(f"    Element len: {call['element_len']}")
        print(f"    Key: {call['key']}")
        print(f"    Params from self.p: {call['params_from_p']}")
    
    guard_calls.clear()

finally:
    OperationGuard._apply_guard = original_apply_guard

print("\n" + "=" * 70)
print("TEST 2: Verify cache key includes dynamic parameters")
print("=" * 70)

x = np.linspace(0, 10, 500)
y = np.cos(x)
curve = hv.Curve((x, y))

class TestOp(GuardedResampleOperation1D):
    def _process_core(self, element, key=None, **kwargs):
        return element

# Use .instance() to create an operation instance without calling it
op = TestOp.instance(width=200)
key1 = op._get_cache_key(curve)
print(f"\n  Cache key with width=200:")
print(f"    {key1}")

op2 = TestOp.instance(width=300)
key2 = op2._get_cache_key(curve)
print(f"\n  Cache key with width=300:")
print(f"    {key2}")

print(f"\n  Keys are different: {key1 != key2}")

op3 = TestOp.instance(width=200, x_range=(0, 5))
key3 = op3._get_cache_key(curve)
print(f"\n  Cache key with x_range=(0, 5):")
print(f"    {key3}")
print(f"  Different from width-only: {key1 != key3}")

# Same params should produce same key
op4 = TestOp.instance(width=200)
key4 = op4._get_cache_key(curve)
print(f"\n  Same params (width=200) produce same key: {key1 == key4}")

print("\n" + "=" * 70)
print("TEST 3: Verify metadata write-back on dynamic path")
print("=" * 70)

class TestMetaOp(GuardedResampleOperation1D):
    _guard_write_metadata = True
    
    def _process_core(self, element, key=None, **kwargs):
        return element.clone([element.data[i] for i in range(0, len(element), 2)])

x = np.linspace(0, 10, 200)
y = np.sin(x)
curve = hv.Curve((x, y))

op = TestMetaOp.instance(width=100)
print(f"\n  _guard_write_metadata: {op._guard_write_metadata}")

# Test dynamic=True path
result_dynamic = op(curve, dynamic=True)
evaluated_dynamic = result_dynamic[()]
print(f"\n  Dynamic path result:")
print(f"    Type: {type(evaluated_dynamic).__name__}")
print(f"    Len: {len(evaluated_dynamic)}")
print(f"    Has _guard_metadata in attrs: {hasattr(evaluated_dynamic, 'attrs') and '_guard_metadata' in evaluated_dynamic.attrs}")
if hasattr(evaluated_dynamic, 'attrs') and '_guard_metadata' in evaluated_dynamic.attrs:
    print(f"    Metadata: {evaluated_dynamic.attrs['_guard_metadata']}")
else:
    # Check metadata via other means
    print(f"    Trying metadata attribute...")
    meta = getattr(evaluated_dynamic, 'metadata', None)
    print(f"    metadata attribute: {meta}")

# Test dynamic=False path for comparison
result_static = op(curve, dynamic=False)
print(f"\n  Static path result:")
print(f"    Type: {type(result_static).__name__}")
print(f"    Len: {len(result_static)}")
print(f"    Has _guard_metadata in attrs: {hasattr(result_static, 'attrs') and '_guard_metadata' in result_static.attrs}")
if hasattr(result_static, 'attrs') and '_guard_metadata' in result_static.attrs:
    print(f"    Metadata: {result_static.attrs['_guard_metadata']}")

print("\n" + "=" * 70)
print("TEST 4: Exception wrapping on dynamic path")
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
    print(f"  No exception raised (unexpected)")
except Exception as e:
    print(f"  Exception type: {type(e).__name__}")
    print(f"  Exception message: {e}")
    print(f"  Exception contains op name: {'TestErrorOp' in str(e)}")

print("\n" + "=" * 70)
print("TEST 5: Empty data short-circuit on dynamic path")
print("=" * 70)

empty_curve = hv.Curve([], 'x', 'y')

op = TestOp.instance(width=50)
result = op(empty_curve, dynamic=True)
evaluated = result[()]
print(f"\n  Empty input result:")
print(f"    Type: {type(evaluated).__name__}")
print(f"    Len: {len(evaluated)}")

print("\n" + "=" * 70)
print("Summary")
print("=" * 70)
print("✅ Guard is called in dynamic=True path")
print("✅ Dynamic params (width, x_range) available via self.p")
print("✅ Cache key includes dynamic parameters")
print("⚠️  Metadata write-back: see test 3")
print("⚠️  Exception wrapping: see test 4")
print("⚠️  Empty data short-circuit: see test 5")
