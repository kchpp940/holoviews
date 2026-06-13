"""Test guard coverage on dynamic=True path."""
import numpy as np
import holoviews as hv
from holoviews.operation.downsample import downsample1d
from holoviews.operation.guard import GuardedOperationMixin, OperationGuard
from holoviews.core.operation import Operation

hv.extension('bokeh')

# Test 1: Verify downsample1d dynamic=True path calls guard
print("=" * 60)
print("Test 1: downsample1d dynamic=True path")
print("=" * 60)

# Monkey-patch to trace calls
original_apply_guard = OperationGuard._apply_guard
call_count = [0]

def traced_apply_guard(self, element, key=None, process_fn=None, **kwargs):
    call_count[0] += 1
    print(f"  ✅ _apply_guard called #{call_count[0]}:")
    print(f"     - element type: {type(element).__name__}")
    print(f"     - len(element): {len(element) if hasattr(element, '__len__') else 'N/A'}")
    print(f"     - key: {key}")
    print(f"     - self.p.width: {getattr(self.p, 'width', 'N/A')}")
    print(f"     - kwargs keys: {list(kwargs.keys())}")
    return original_apply_guard(self, element, key, process_fn, **kwargs)

OperationGuard._apply_guard = traced_apply_guard

try:
    # Create test data
    x = np.linspace(0, 10, 1000)
    y = np.sin(x)
    curve = hv.Curve((x, y))
    
    # Test dynamic=True (default)
    print(f"\n  Input curve: len={len(curve)}")
    print(f"  downsample1d.dynamic default: {downsample1d.dynamic}")
    
    # This should return a DynamicMap
    result = downsample1d(curve, width=100)
    print(f"  Result type: {type(result).__name__}")
    
    # Now actually evaluate the DynamicMap to trigger frame execution
    if isinstance(result, hv.DynamicMap):
        print(f"  DynamicMap kdims: {result.kdims}")
        print(f"  Evaluating DynamicMap...")
        # Trigger frame evaluation
        evaluated = result[()]
        print(f"  Evaluated result type: {type(evaluated).__name__}")
        print(f"  Evaluated len: {len(evaluated)}")
        print(f"  _apply_guard called {call_count[0]} times")
    else:
        print(f"  Result len: {len(result)}")
    
    print(f"\n  Total _apply_guard calls: {call_count[0]}")
    
finally:
    OperationGuard._apply_guard = original_apply_guard

# Test 2: Check if process_element is the real entry point
print("\n" + "=" * 60)
print("Test 2: Trace process_element vs _process call order")
print("=" * 60)

original_process_element = Operation.process_element
original_apply = Operation._apply
original_process = Operation._process

trace = []

def traced_process_element(self, element, key, **params):
    trace.append(('process_element', type(self).__name__, list(params.keys())))
    print(f"  ↗️ process_element called: {type(self).__name__}, params={list(params.keys())}")
    return original_process_element(self, element, key, **params)

def traced_apply(self, element, key=None):
    trace.append(('_apply', type(self).__name__))
    print(f"  → _apply called: {type(self).__name__}")
    return original_apply(self, element, key)

def traced_process(self, element, key=None, **kwargs):
    trace.append(('_process', type(self).__name__, list(kwargs.keys())))
    print(f"  → _process called: {type(self).__name__}, kwargs={list(kwargs.keys())}")
    if hasattr(super(type(self), self), '_process'):
        return super(type(self), self)._process(element, key, **kwargs)
    return original_process(self, element, key)

Operation.process_element = traced_process_element
Operation._apply = traced_apply
Operation._process = traced_process

try:
    call_count[0] = 0
    OperationGuard._apply_guard = traced_apply_guard
    
    x = np.linspace(0, 10, 500)
    y = np.cos(x)
    curve = hv.Curve((x, y))
    
    print("\n  Testing dynamic=False (direct path):")
    result1 = downsample1d(curve, width=50, dynamic=False)
    print(f"  Call order: {[t[0] for t in trace]}")
    
    trace.clear()
    
    print("\n  Testing dynamic=True (DynamicMap path):")
    result2 = downsample1d(curve, width=50, dynamic=True)
    print(f"  Before evaluation - Call order: {[t[0] for t in trace]}")
    
    evaluated = result2[()]
    print(f"  After evaluation - Call order: {[t[0] for t in trace]}")
    print(f"  Full trace:")
    for t in trace:
        print(f"    {t}")
    
finally:
    Operation.process_element = original_process_element
    Operation._apply = original_apply
    Operation._process = original_process
    OperationGuard._apply_guard = original_apply_guard

print("\n" + "=" * 60)
print("Summary")
print("=" * 60)
print("Key insight: process_element is the entry point for BOTH paths.")
print("Dynamic parameters (x_range, etc.) are available in process_element's **params.")
print("_apply and _process lose these params in their signatures.")
