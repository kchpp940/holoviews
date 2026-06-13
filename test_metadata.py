"""Test metadata write-back on dynamic path."""
import numpy as np
import holoviews as hv
from holoviews.operation.guard import OperationGuard
from holoviews.operation.resample import GuardedResampleOperation1D

hv.extension('bokeh')

print("=" * 70)
print("TEST: Metadata write-back on dynamic path")
print("=" * 70)

class TestMetaOp(GuardedResampleOperation1D):
    _guard_write_metadata = True
    _guard_record_time = True
    
    def _process_core(self, element, key=None, **kwargs):
        return element.clone(
            element.data.iloc[::2] if hasattr(element.data, 'iloc') else element.data
        )

x = np.linspace(0, 10, 200)
y = np.sin(x)
curve = hv.Curve((x, y))

# Test 1: dynamic=False
print("\n--- Test 1: dynamic=False ---")
op = TestMetaOp.instance(width=100)
result_static = op(curve, dynamic=False)
print(f"Result type: {type(result_static).__name__}")
print(f"Result len: {len(result_static)}")
print(f"Has attrs: {hasattr(result_static, 'attrs')}")
if hasattr(result_static, 'attrs'):
    print(f"attrs keys: {list(result_static.attrs.keys())}")
    print(f"_guard_metadata: {result_static.attrs.get('_guard_metadata', 'NOT FOUND')}")

# Test 2: dynamic=True
print("\n--- Test 2: dynamic=True ---")
result_dynamic = op(curve, dynamic=True)
evaluated = result_dynamic[()]
print(f"Result type: {type(evaluated).__name__}")
print(f"Result len: {len(evaluated)}")
print(f"Has attrs: {hasattr(evaluated, 'attrs')}")
if hasattr(evaluated, 'attrs'):
    print(f"attrs keys: {list(evaluated.attrs.keys())}")
    print(f"_guard_metadata: {evaluated.attrs.get('_guard_metadata', 'NOT FOUND')}")

# Test 3: Check what metadata is available on the element
print("\n--- Test 3: Element metadata investigation ---")
print(f"dir(result_static) - metadata related: {[x for x in dir(result_static) if 'meta' in x.lower() or 'attr' in x.lower()]}")
print(f"type(result_static).param names: {[p for p in type(result_static).param if 'meta' in p.lower()]}")

# Try to see if we can write metadata via clone
print("\n--- Test 4: Clone with metadata test ---")
try:
    test_clone = curve.clone(metadata={"test": "value"})
    print(f"Clone with metadata works: {hasattr(test_clone, 'metadata')}")
    if hasattr(test_clone, 'metadata'):
        print(f"  metadata value: {test_clone.metadata}")
except Exception as e:
    print(f"Clone with metadata failed: {e}")

# Try to see if attrs works
print("\n--- Test 5: attrs test ---")
try:
    test_attrs = curve.clone()
    test_attrs.attrs["test_key"] = "test_value"
    print(f"Setting attrs works: {test_attrs.attrs.get('test_key')}")
except Exception as e:
    print(f"Setting attrs failed: {e}")

print("\n" + "=" * 70)
print("Summary")
print("=" * 70)
