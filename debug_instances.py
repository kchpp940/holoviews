import holoviews as hv
from holoviews.plotting import LifecyclePhase, LifecycleContext, LifecycleHook, hook_for
from holoviews.plotting.bokeh.plot import BokehPlot
from holoviews.plotting.plotly.plot import PlotlyPlot
from holoviews.plotting.mpl.plot import MPLPlot

class InstanceCountHook(LifecycleHook):
    def __init__(self):
        super().__init__()
        self.plot_ids = []
    
    @hook_for(LifecyclePhase.PRE_INIT, when="after")
    def track_instance(self, ctx):
        plot_id = id(ctx.plot)
        plot_type = type(ctx.plot).__name__
        self.plot_ids.append((plot_id, plot_type))
        print(f"  [PRE_INIT] {plot_type} (id={plot_id})")
        return ctx

print("=" * 60)
print("Bokeh backend:")
print("=" * 60)
hv.extension('bokeh')
hook1 = InstanceCountHook()
BokehPlot.register_lifecycle_hook(hook1)
curve = hv.Curve([1, 2, 3])
plot = hv.render(curve, backend='bokeh')
print(f"  Total plot instances: {len(set(id for id, _ in hook1.plot_ids))}")
BokehPlot._class_lifecycle_hooks.clear()

print()
print("=" * 60)
print("Plotly backend:")
print("=" * 60)
hv.extension('plotly')
hook2 = InstanceCountHook()
PlotlyPlot.register_lifecycle_hook(hook2)
curve = hv.Curve([1, 2, 3])
plot = hv.render(curve, backend='plotly')
print(f"  Total plot instances: {len(set(id for id, _ in hook2.plot_ids))}")
PlotlyPlot._class_lifecycle_hooks.clear()

print()
print("=" * 60)
print("Matplotlib backend:")
print("=" * 60)
hv.extension('matplotlib')
hook3 = InstanceCountHook()
MPLPlot.register_lifecycle_hook(hook3)
curve = hv.Curve([1, 2, 3])
plot = hv.render(curve, backend='matplotlib')
print(f"  Total plot instances: {len(set(id for id, _ in hook3.plot_ids))}")
print(f"  Plot IDs: {hook3.plot_ids}")
MPLPlot._class_lifecycle_hooks.clear()
