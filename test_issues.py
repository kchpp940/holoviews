import numpy as np
import pandas as pd
import xarray as xr
import holoviews as hv
from holoviews.core.util import bound_range, compute_density, dt_to_int
from holoviews.core.data.grid import GridInterface
from holoviews.core.data.xarray import XArrayInterface

print("=== Test 1: Regular grid with datetime coordinates ===")
dates = pd.date_range("2020-01-01", periods=5, freq="D")
print("Datetime coords:", dates.values)
print("dtype:", dates.values.dtype)

# Test bound_range
l, r, density, invert = bound_range(dates.values, None)
print(f"bound_range result: l={l}, r={r}, density={density}, invert={invert}")
print(f"l type: {type(l)}, r type: {type(r)}")
print(f"Expected l: {dates.values[0] - np.timedelta64(12, 'h')}")
print(f"Expected r: {dates.values[-1] + np.timedelta64(12, 'h')}")

# Test Image construction with datetime coords
z = np.random.rand(5, 5)
img = hv.Image((dates.values, dates.values, z))
print(f"\nImage bounds: {img.bounds.lbrt()}")
print(f"Image range(0): {img.range(0)}")
print(f"Image range(1): {img.range(1)}")

print("\n=== Test 2: Reversed (descending) coordinates ===")
x_rev = np.linspace(10, 0, 5)  # descending
y_rev = np.linspace(10, 0, 5)  # descending
print("x_rev:", x_rev)
print("y_rev:", y_rev)

# Test bound_range on reversed coords
l, r, density, invert = bound_range(x_rev, None)
print(f"\nbound_range x_rev: l={l}, r={r}, density={density}, invert={invert}")

# Test Image with reversed coords
z = np.arange(25).reshape(5, 5).astype(float)
img_rev = hv.Image((x_rev, y_rev, z))
print(f"\nReversed Image bounds: {img_rev.bounds.lbrt()}")
print(f"Reversed Image range(0): {img_rev.range(0)}")
print(f"Reversed Image range(1): {img_rev.range(1)}")

# Check if the data is correctly oriented
print(f"\nOriginal Z[0,0] (top-left in descending): {z[0,0]}")
print(f"Image data at (10, 10) corner: should be z[0,0]={z[0,0]}")

print("\n=== Test 3: GridInterface coords with edges and ordering ===")
data = {"x": x_rev, "y": y_rev, "z": z}
ds = hv.Dataset(data, kdims=["x", "y"], vdims=["z"], datatype=["grid"])
print("Grid coords x (ordered=False):", ds.interface.coords(ds, "x", ordered=False))
print("Grid coords x (ordered=True):", ds.interface.coords(ds, "x", ordered=True))
print("Grid coords x (ordered=True, edges=True):", ds.interface.coords(ds, "x", ordered=True, edges=True))

print("\n=== Test 4: XArray with datetime coords ===")
da = xr.DataArray(
    z,
    coords={"time": dates, "y": np.arange(5)},
    dims=["y", "time"],
)
img_xr = hv.Image(da)
print(f"XArray Image bounds: {img_xr.bounds.lbrt()}")
print(f"XArray Image range(0): {img_xr.range(0)}")
print(f"XArray Image range(1): {img_xr.range(1)}")
print(f"XArray dimension_values(0, False): {img_xr.dimension_values(0, False)}")

print("\n=== Test 5: QuadMesh with edges ===")
# QuadMesh with edges (shape N+1)
x_edges = np.linspace(0, 10, 6)
y_edges = np.linspace(0, 10, 6)
z_qm = np.arange(25).reshape(5, 5).astype(float)
qm = hv.QuadMesh((x_edges, y_edges, z_qm))
print(f"QuadMesh range(0): {qm.range(0)}")
print(f"QuadMesh range(1): {qm.range(1)}")
print(f"QuadMesh coords x (edges=False): {qm.interface.coords(qm, 'x', edges=False)}")
print(f"QuadMesh coords x (edges=True): {qm.interface.coords(qm, 'x', edges=True)}")
print(f"Expected x edges: {x_edges}")

print("\n=== Test 6: QuadMesh with reversed edges ===")
x_edges_rev = np.linspace(10, 0, 6)
y_edges_rev = np.linspace(10, 0, 6)
qm_rev = hv.QuadMesh((x_edges_rev, y_edges_rev, z_qm))
print(f"Reversed QuadMesh range(0): {qm_rev.range(0)}")
print(f"Reversed QuadMesh range(1): {qm_rev.range(1)}")
print(f"Reversed QuadMesh coords x (ordered=True, edges=True): {qm_rev.interface.coords(qm_rev, 'x', ordered=True, edges=True)}")
print(f"Expected x edges (sorted): {np.sort(x_edges_rev)}")

print("\n=== Test 7: Irregular grid (2D coords) ===")
x_1d = np.linspace(0, 10, 5)
y_1d = np.linspace(0, 10, 5)
X, Y = np.meshgrid(x_1d, y_1d)
X_irr = X + 0.1 * Y  # slightly irregular
Y_irr = Y + 0.1 * X
z_irr = np.sin(X) * np.cos(Y)
qm_irr = hv.QuadMesh((X_irr, Y_irr, z_irr))
print(f"Irregular QuadMesh range(0): {qm_irr.range(0)}")
print(f"Irregular QuadMesh range(1): {qm_irr.range(1)}")
print(f"Expected x range: ({X_irr.min()}, {X_irr.max()})")
print(f"Expected y range: ({Y_irr.min()}, {Y_irr.max()})")

print("\n=== Test 8: XArrayInterface range for binned data ===")
# XArray with binned (_binned=True) data
da_binned = xr.DataArray(
    z_qm,
    coords={"x": x_edges, "y": y_edges},
    dims=["y", "x"],
)
ds_xr = hv.Dataset(da_binned, kdims=["x", "y"], vdims=["z"], datatype=["xarray"])
ds_xr._binned = True
print(f"XArray binned range(0): {ds_xr.range(0)}")
print(f"XArray binned range(1): {ds_xr.range(1)}")
print(f"Expected: ({x_edges.min()}, {x_edges.max()})")

print("\n=== Test 9: Interface coordinates comparison (ordered vs not) ===")
x_desc = np.array([5.0, 4.0, 3.0, 2.0, 1.0])
y_asc = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
z_test = np.ones((5, 5))
data_dict = {"x": x_desc, "y": y_asc, "z": z_test}
ds_test = hv.Dataset(data_dict, kdims=["x", "y"], vdims=["z"], datatype=["grid"])

print(f"x (unordered): {ds_test.interface.coords(ds_test, 'x', ordered=False)}")
print(f"x (ordered): {ds_test.interface.coords(ds_test, 'x', ordered=True)}")
print(f"x (ordered, edges): {ds_test.interface.coords(ds_test, 'x', ordered=True, edges=True)}")
print(f"x (unordered, edges): {ds_test.interface.coords(ds_test, 'x', ordered=False, edges=True)}")

# Now test edges inference for unordered
expected_edges_unordered = GridInterface._infer_interval_breaks(x_desc)
print(f"_infer_interval_breaks on x_desc directly: {expected_edges_unordered}")
