import traceback
import holoviews as hv
from holoviews.plotting import LifecyclePhase, LifecycleContext, LifecycleHook, hook_for
from holoviews.plotting.mpl.plot import MPLPlot

hv.extension('matplotlib')

class DebugCreateHook(LifecycleHook):
    def __init__(self):
        super().__init__()
        self.first_plot_id = None
        self.second_plot_id = None
    
    @hook_for(LifecyclePhase.PRE_INIT, when="after")
    def track_init(self, ctx):
        plot_id = id(ctx.plot)
        plot_type = type(ctx.plot).__name__
        
        if self.first_plot_id is None:
            self.first_plot_id = plot_id
            print(f"\n[1st plot] {plot_type} (id={plot_id})")
            print("  Stack trace:")
            stack = traceback.extract_stack()
            for frame in stack[-15:-1]:
                print(f"    {frame.filename.split('/')[-1]}:{frame.lineno} - {frame.name}")
        elif self.second_plot_id is None and plot_id != self.first_plot_id:
            self.second_plot_id = plot_id
            print(f"\n[2nd plot] {plot_type} (id={plot_id})")
            print("  Stack trace:")
            stack = traceback.extract_stack()
            for frame in stack[-15:-1]:
                print(f"    {frame.filename.split('/')[-1]}:{frame.lineno} - {frame.name}")
        else:
            print(f"\n[plot call] {plot_type} (id={plot_id})")
        
        return ctx

hook = DebugCreateHook()
MPLPlot.register_lifecycle_hook(hook)

print("=" * 60)
print("Calling hv.render(curve)...")
print("=" * 60)

curve = hv.Curve([1, 2, 3, 4, 5])
plot = hv.render(curve, backend='matplotlib')

print(f"\n{'=' * 60}")
print(f"First plot ID: {hook.first_plot_id}")
print(f"Second plot ID: {hook.second_plot_id}")
print(f"Final returned plot ID: {id(plot) if plot else None}")
print(f"Final plot type: {type(plot).__name__ if plot else None}")

MPLPlot._class_lifecycle_hooks.clear()
