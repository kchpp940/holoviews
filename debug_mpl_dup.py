import traceback
import holoviews as hv
from holoviews.plotting import LifecyclePhase, LifecycleContext, LifecycleHook, hook_for
from holoviews.plotting.mpl.plot import MPLPlot

hv.extension('matplotlib')

class DebugPhaseHook(LifecycleHook):
    def __init__(self):
        super().__init__()
        self.phase_calls = []
    
    @hook_for(LifecyclePhase.CREATE_FIGURE, when="before")
    def track_all_phases(self, ctx):
        call_info = {
            "phase": "CREATE_FIGURE",
            "when": "before",
            "plot_type": type(ctx.plot).__name__,
            "plot_id": id(ctx.plot),
            "stack": traceback.extract_stack()[-10:-1],
        }
        self.phase_calls.append(call_info)
        print(f"\n[DEBUG] CREATE_FIGURE called for {type(ctx.plot).__name__} (id={id(ctx.plot)})")
        print(f"  Call stack:")
        for frame in call_info["stack"][-5:]:
            print(f"    {frame.filename}:{frame.lineno} - {frame.name}")
        return ctx
    
    @hook_for(LifecyclePhase.CREATE_FIGURE, when="after")
    def track_after_figure(self, ctx):
        call_info = {
            "phase": "CREATE_FIGURE",
            "when": "after",
            "plot_type": type(ctx.plot).__name__,
            "plot_id": id(ctx.plot),
        }
        self.phase_calls.append(call_info)
        print(f"[DEBUG] CREATE_FIGURE [after] for {type(ctx.plot).__name__} (id={id(ctx.plot)})")
        return ctx

hook = DebugPhaseHook()
MPLPlot.register_lifecycle_hook(hook)

print("=" * 60)
print("Rendering a simple Curve...")
print("=" * 60)
curve = hv.Curve([1, 2, 3, 4, 5])
plot = hv.render(curve, backend='matplotlib')

print(f"\n{'=' * 60}")
print(f"Total phase calls: {len(hook.phase_calls)}")
print(f"Unique plot IDs: {set(c['plot_id'] for c in hook.phase_calls)}")
print(f"Plot types: {set(c['plot_type'] for c in hook.phase_calls)}")
for i, call in enumerate(hook.phase_calls):
    print(f"  {i+1}. {call['phase']} [{call['when']}] - {call['plot_type']} (id={call['plot_id']})")

MPLPlot._class_lifecycle_hooks.clear()
