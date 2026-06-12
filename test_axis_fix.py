import holoviews as hv
from holoviews.plotting import LifecyclePhase, LifecycleContext, LifecycleHook, hook_for
from holoviews.plotting.bokeh.plot import BokehPlot

hv.extension('bokeh')

class TestAxisLabelHook(LifecycleHook):
    def __init__(self):
        super().__init__()
        self.axis_label_history = []
    
    @hook_for(LifecyclePhase.CREATE_AXES, when="after")
    def modify_axis_label(self, ctx):
        xaxis, yaxis = ctx.axes
        old_label = xaxis.axis_label
        xaxis.axis_label = "X-Label-Modified"
        self.axis_label_history.append(("CREATE_AXES after", xaxis.axis_label))
        print(f"  CREATE_AXES [after]: xaxis label = '{xaxis.axis_label}' (was '{old_label}')")
        return ctx
    
    @hook_for(LifecyclePhase.CREATE_LEGEND, when="after")
    def check_label_after_legend(self, ctx):
        xaxis, yaxis = ctx.axes
        self.axis_label_history.append(("CREATE_LEGEND after", xaxis.axis_label))
        print(f"  CREATE_LEGEND [after]: xaxis label = '{xaxis.axis_label}'")
        return ctx
    
    @hook_for(LifecyclePhase.CREATE_COLORBAR, when="after")
    def check_label_after_colorbar(self, ctx):
        xaxis, yaxis = ctx.axes
        self.axis_label_history.append(("CREATE_COLORBAR after", xaxis.axis_label))
        print(f"  CREATE_COLORBAR [after]: xaxis label = '{xaxis.axis_label}'")
        return ctx
    
    @hook_for(LifecyclePhase.CREATE_TOOLS, when="after")
    def check_label_after_tools(self, ctx):
        xaxis, yaxis = ctx.axes
        self.axis_label_history.append(("CREATE_TOOLS after", xaxis.axis_label))
        print(f"  CREATE_TOOLS [after]: xaxis label = '{xaxis.axis_label}'")
        return ctx
    
    @hook_for(LifecyclePhase.FINALIZE_STYLE, when="after")
    def check_label_final(self, ctx):
        xaxis, yaxis = ctx.axes
        self.axis_label_history.append(("FINALIZE_STYLE after", xaxis.axis_label))
        print(f"  FINALIZE_STYLE [after]: xaxis label = '{xaxis.axis_label}'")
        return ctx

hook = TestAxisLabelHook()
BokehPlot.register_lifecycle_hook(hook)

print("=" * 60)
print("测试 Bokeh CREATE_AXES 阶段修改是否被保留")
print("=" * 60)

curve = hv.Curve([1, 2, 3, 4, 5], label="Test")
plot = hv.render(curve, backend='bokeh')

print(f"\n最终结果: plot.xaxis[0].axis_label = '{plot.xaxis[0].axis_label}'")
print()

# 验证所有阶段标签都保持一致
all_labels = [label for _, label in hook.axis_label_history]
assert len(set(all_labels)) == 1, f"标签不一致: {hook.axis_label_history}"
assert plot.xaxis[0].axis_label == "X-Label-Modified", f"最终标签未保留: {plot.xaxis[0].axis_label}"

print("✓✓✓ CREATE_AXES 阶段的修改在所有后续阶段都被保留 ✓✓✓")

BokehPlot._class_lifecycle_hooks.clear()
