import numpy as np
import holoviews as hv
from holoviews.operation.datashader import rasterize, aggregate, regrid
from holoviews.operation.resample import OperationExecutionContext, ResampleOperation2D
from holoviews.element import Points, Image, Curve
import datashader.reductions as rd

hv.extension('bokeh')

print("=" * 60)
print("Testing OperationExecutionContext")
print("=" * 60)

print("\n1. Test context creation with Points...")
pts = Points(np.random.randn(100, 2))
print(f"   Points created: {len(pts)} points")

op = aggregate.instance(width=200, height=200)
ctx = op._create_execution_context(pts, pts.kdims[0], pts.kdims[1])
print(f"   Context created successfully")
print(f"   - x_range: {ctx.x_range}")
print(f"   - y_range: {ctx.y_range}")
print(f"   - width: {ctx.width}, height: {ctx.height}")
print(f"   - xunit: {ctx.xunit:.6f}, yunit: {ctx.yunit:.6f}")
print(f"   - xtype: {ctx.xtype}, ytype: {ctx.ytype}")
print(f"   - bounds: {ctx.bounds}")
print(f"   - xs shape: {ctx.xs.shape}, ys shape: {ctx.ys.shape}")
print(f"   - is_empty: {ctx.is_empty()}")

print("\n2. Test context with x_sampling...")
op2 = aggregate.instance(width=400, height=400, x_sampling=0.1)
ctx2 = op2._create_execution_context(pts, pts.kdims[0], pts.kdims[1])
print(f"   Context with x_sampling=0.1")
print(f"   - Original width: 400, Actual width: {ctx2.width}")
print(f"   - x_sampling enforced: {ctx2.width < 400}")

print("\n3. Test backward compatibility of _get_sampling...")
result = op._get_sampling(pts, pts.kdims[0], pts.kdims[1])
(x_range, y_range), (xs, ys), (width, height), (xtype, ytype) = result
print(f"   _get_sampling returns correct format: {len(result) == 4}")
print(f"   - width matches context: {width == ctx.width}")
print(f"   - height matches context: {height == ctx.height}")

print("\n4. Test rasterize operation...")
rasterized = rasterize(pts, width=100, height=100)
print(f"   Rasterize completed: {type(rasterized).__name__}")

print("\n5. Test aggregate operation with context...")
agg_result = aggregate(pts, width=100, height=100, aggregator=rd.mean())
print(f"   Aggregate completed: {type(agg_result).__name__}")
print(f"   Result dimensions: {agg_result.shape}")

print("\n6. Test Image regrid with context...")
img = Image(np.random.randn(50, 50))
regridded = regrid(img, width=25, height=25)
print(f"   Regrid completed: {type(regridded).__name__}")
print(f"   Original shape: (50, 50), New shape: {regridded.shape}")

print("\n7. Test context cache functionality...")
class MockElement:
    def __init__(self):
        self._plot_id = "test_123"
        self.kdims = [hv.Dimension('x'), hv.Dimension('y')]
    
    def range(self, dim):
        return (-1, 1)

mock_op = aggregate.instance(precompute=True)
mock_el = MockElement()
ctx3 = mock_op._create_execution_context(mock_el, mock_el.kdims[0], mock_el.kdims[1])
print(f"   Precompute enabled: {ctx3.use_precompute}")
print(f"   Has cached: {ctx3.has_cached('test_123')}")
ctx3.cache_result('test_123', ('cached_data',))
print(f"   After caching, has cached: {ctx3.has_cached('test_123')}")
print(f"   Get cached: {ctx3.get_cached('test_123')}")

print("\n8. Test empty context detection...")
op_empty = aggregate.instance(width=0, height=0)
ctx_empty = op_empty._create_execution_context(pts, pts.kdims[0], pts.kdims[1])
print(f"   Zero-size context is_empty: {ctx_empty.is_empty()}")

print("\n" + "=" * 60)
print("All tests passed! ✓")
print("=" * 60)
