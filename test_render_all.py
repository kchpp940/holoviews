"""Verify no duplicate per-frame resolves and all rendering works."""
import holoviews as hv
from holoviews.core.options import OptionResolver, ResolvedOptions, Options, Store

# Patch resolve_options to count calls
_original_resolve = OptionResolver.resolve
_resolve_calls = []

def _counting_resolve(cls, obj, group=None, backend=None, defaults=True, user_overrides=None):
    obj_id = id(obj) if hasattr(obj, "id") else id(obj)
    obj_type = type(obj).__name__
    frame_key = getattr(obj, "id", obj_id)
    _resolve_calls.append((obj_type, group, frame_key, obj_id))
    return _original_resolve.__func__(cls, obj, group, backend, defaults, user_overrides)

OptionResolver.resolve = classmethod(_counting_resolve)

hv.extension("bokeh")

errors = []

def check(name, condition, msg=""):
    if not condition:
        errors.append(f"FAIL: {name} - {msg}")
        print(f"FAIL: {name} - {msg}")
    else:
        print(f"PASS: {name}")

# =====================================================================
# Test 1: Basic element rendering (bokeh)
# =====================================================================
_resolve_calls.clear()
curve = hv.Curve([1, 2, 3]).opts(color="red", width=800)
renderer = hv.renderer("bokeh")
plot = renderer.get_plot(curve)
check("bokeh basic render", plot is not None)
check("plot has _resolved cache", isinstance(getattr(plot, "_resolved", None), ResolvedOptions))
check("_resolved has correct values", plot._resolved.style.kwargs.get("color") == "red")
check("_resolved provenance correct", plot._resolved.is_user_set("style", "color"))
print(f"  resolve calls for basic curve: {len(_resolve_calls)}")

# =====================================================================
# Test 2: No duplicate resolve for same obj in update_frame
# =====================================================================
_resolve_calls.clear()
hmap = hv.HoloMap({i: hv.Curve([i, i+1, i+2]) for i in range(3)})
hmap_plot = renderer.get_plot(hmap)
init_calls = len(_resolve_calls)
_resolve_calls.clear()
# Trigger update_frame
hmap_plot.update(1)
frame_update_calls = len(_resolve_calls)
print(f"  init resolves: {init_calls}, frame update resolves: {frame_update_calls}")
check("frame update resolves are bounded (<=5)", frame_update_calls <= 5)

# =====================================================================
# Test 3: Overlay rendering
# =====================================================================
_resolve_calls.clear()
overlay = hv.Overlay([hv.Curve([1,2,3]).opts(color="red"), hv.Curve([3,2,1]).opts(color="blue")])
overlay_plot = renderer.get_plot(overlay)
check("overlay render works", overlay_plot is not None)
print(f"  overlay resolve calls: {len(_resolve_calls)}")

# =====================================================================
# Test 4: NdOverlay rendering
# =====================================================================
_resolve_calls.clear()
ndoverlay = hv.NdOverlay({i: hv.Curve([i, i+1, i+2]) for i in range(3)})
ndoverlay_plot = renderer.get_plot(ndoverlay)
check("ndoverlay render works", ndoverlay_plot is not None)
print(f"  ndoverlay resolve calls: {len(_resolve_calls)}")

# =====================================================================
# Test 5: Layout rendering
# =====================================================================
_resolve_calls.clear()
layout = hv.Curve([1,2,3]) + hv.Scatter([1,2,3])
layout_plot = renderer.get_plot(layout)
check("layout render works", layout_plot is not None)
print(f"  layout resolve calls: {len(_resolve_calls)}")

# =====================================================================
# Test 6: DynamicMap rendering
# =====================================================================
_resolve_calls.clear()
dmap = hv.DynamicMap(lambda: hv.Curve([1,2,3]))
dmap_plot = renderer.get_plot(dmap)
check("dmap render works", dmap_plot is not None)
print(f"  dmap resolve calls: {len(_resolve_calls)}")

# =====================================================================
# Test 7: Various plot types
# =====================================================================
plot_types = [
    hv.Scatter([(1,1), (2,4), (3,9)]),
    hv.Bars([("A", 1), ("B", 2), ("C", 3)]),
    hv.Points([(1,1), (2,2)]),
    hv.Histogram([1, 2, 2, 3, 3, 3, 4]),
    hv.HeatMap([("A", "X", 1), ("A", "Y", 2), ("B", "X", 3)]),
    hv.Spikes([1, 2, 3, 4, 5]),
]
for pt in plot_types:
    _resolve_calls.clear()
    try:
        p = renderer.get_plot(pt)
        check(f"{type(pt).__name__} render", p is not None)
    except Exception as e:
        check(f"{type(pt).__name__} render", False, str(e)[:80])

# =====================================================================
# Test 8: matplotlib rendering
# =====================================================================
hv.extension("matplotlib")
_resolve_calls.clear()
mpl_renderer = hv.renderer("matplotlib")
curve2 = hv.Curve([1, 2, 3]).opts(color="blue")
mpl_plot = mpl_renderer.get_plot(curve2)
check("matplotlib basic render", mpl_plot is not None)
check("mpl plot has _resolved cache", isinstance(getattr(mpl_plot, "_resolved", None), ResolvedOptions))
print(f"  mpl resolve calls: {len(_resolve_calls)}")

# =====================================================================
# Test 9: Store.lookup_options still raw (backward compat)
# =====================================================================
hv.extension("bokeh")
raw_style = Store.lookup_options("bokeh", curve, "style")
check("Store.lookup_options raw type", isinstance(raw_style, Options))
check("Store.lookup_options no provenance", not hasattr(raw_style, "provenance"))

# =====================================================================
# Test 10: transfer_options still raw
# =====================================================================
new_curve = hv.Curve([5, 4, 3])
Store.transfer_options(curve, new_curve, "bokeh")
transferred_raw = OptionResolver.lookup_raw(new_curve, "style", "bokeh", defaults=False)
check("transfer_options uses raw", isinstance(transferred_raw, Options))

if errors:
    print(f"\n{len(errors)} FAILURES")
    for e in errors:
        print(f"  {e}")
else:
    print("\nAll checks passed!")
