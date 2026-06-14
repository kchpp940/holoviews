import warnings
warnings.filterwarnings("ignore")

# First, fix the issue temporarily by manually checking what's in registry
import holoviews as hv
from holoviews.core.options import Store

# Let's check what gets registered
print("=== Inspecting Store.registry ===")
print()

# Check if there's a manual register call we can trace
from holoviews.plotting.bokeh import CurvePlot
print("CurvePlot type:", type(CurvePlot))
print("CurvePlot.__name__:", getattr(CurvePlot, "__name__", "NO __name__"))
print("isinstance CurvePlot type:", isinstance(CurvePlot, type))

# Check if it's a PlotSelector
from holoviews.plotting.plot import PlotSelector
print()
print("PlotSelector check:")
print("isinstance(CurvePlot, PlotSelector):", isinstance(CurvePlot, PlotSelector))
if isinstance(CurvePlot, PlotSelector):
    print("PlotSelector has plot_fn:", hasattr(CurvePlot, 'plot_fn'))
    print("PlotSelector .plot_fn:", getattr(CurvePlot, 'plot_fn', 'N/A'))
    fn = getattr(CurvePlot, 'plot_fn', None)
    if fn is not None:
        print("plot_fn.__name__:", getattr(fn, '__name__', 'N/A'))

# Now test the actual code path that's failing
print()
print("=== Testing the failing code path ===")
try:
    from holoviews.core.schema import build_plot_schema
    plot_class = CurvePlot
    # This is what we call now
    s = build_plot_schema(plot_class=plot_class)
    print("build_plot_schema OK")
except Exception as e:
    print(f"build_plot_schema FAILED: {e}")
    import traceback
    traceback.print_exc()

# What should we pass instead?
print()
print("=== Trying with .plot_fn ===")
if isinstance(CurvePlot, PlotSelector):
    fn = CurvePlot.plot_fn
    try:
        s2 = build_plot_schema(plot_class=fn)
        print("build_plot_schema with plot_fn OK, specs:", sorted(s2._specs.keys())[:10])
    except Exception as e:
        print(f"Still failed: {e}")
