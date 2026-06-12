import holoviews as hv
from holoviews.plotting import LifecyclePhase, LifecycleContext, LifecycleHook, hook_for
from holoviews.plotting.mpl.plot import MPLPlot

hv.extension('matplotlib')

class TestMPLAxisHook(LifecycleHook):
    def __init__(self):
        super().__init__()
        self.xlabel_history = []
    
    @hook_for(LifecyclePhase.CREATE_AXES, when="after")
    def modify_xlabel(self, ctx):
        old_label = ctx.axes.get_xlabel()
        ctx.axes.set_xlabel("X-Label-Modified")
        self.xlabel_history.append(("CREATE_AXES after", ctx.axes.get_xlabel()))
        print(f"  CREATE_AXES [after]: xlabel = '{ctx.axes.get_xlabel()}' (was '{old_label}')")
        return ctx
    
    @hook_for(LifecyclePhase.CREATE_LEGEND, when="after")
    def check_after_legend(self, ctx):
        self.xlabel_history.append(("CREATE_LEGEND after", ctx.axes.get_xlabel()))
        print(f"  CREATE_LEGEND [after]: xlabel = '{ctx.axes.get_xlabel()}'")
        return ctx
    
    @hook_for(LifecyclePhase.CREATE_COLORBAR, when="after")
    def check_after_colorbar(self, ctx):
        self.xlabel_history.append(("CREATE_COLORBAR after", ctx.axes.get_xlabel()))
        print(f"  CREATE_COLORBAR [after]: xlabel = '{ctx.axes.get_xlabel()}'")
        return ctx
    
    @hook_for(LifecyclePhase.CREATE_TOOLS, when="after")
    def check_after_tools(self, ctx):
        self.xlabel_history.append(("CREATE_TOOLS after", ctx.axes.get_xlabel()))
        print(f"  CREATE_TOOLS [after]: xlabel = '{ctx.axes.get_xlabel()}'")
        return ctx
    
    @hook_for(LifecyclePhase.FINALIZE_STYLE, when="after")
    def check_final(self, ctx):
        self.xlabel_history.append(("FINALIZE_STYLE after", ctx.axes.get_xlabel()))
        print(f"  FINALIZE_STYLE [after]: xlabel = '{ctx.axes.get_xlabel()}'")
        return ctx

hook = TestMPLAxisHook()
MPLPlot.register_lifecycle_hook(hook)

print("=" * 60)
print("测试 MPL CREATE_AXES 阶段修改是否被保留")
print("=" * 60)

curve = hv.Curve([1, 2, 3, 4, 5], label="Test")
plot = hv.render(curve, backend='matplotlib')

ax = plot.axes[0]
print(f"\n最终结果: ax.get_xlabel() = '{ax.get_xlabel()}'")
print()

# 验证所有阶段标签都保持一致
all_labels = [label for _, label in hook.xlabel_history]
assert len(set(all_labels)) == 1, f"标签不一致: {hook.xlabel_history}"
assert ax.get_xlabel() == "X-Label-Modified", f"最终标签未保留: {ax.get_xlabel()}"

print("✓✓✓ CREATE_AXES 阶段的修改在所有后续阶段都被保留 ✓✓✓")

MPLPlot._class_lifecycle_hooks.clear()
