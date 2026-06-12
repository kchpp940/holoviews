"""Debug MPL legend handles"""
import holoviews as hv

hv.extension("matplotlib", logo=False)

curve1 = hv.Curve([1, 2, 3], label="A")
curve2 = hv.Curve([3, 2, 1], label="B")
overlay = curve1 * curve2

renderer = hv.renderer("matplotlib")
plot = renderer.get_plot(overlay)
fig = renderer.get_plot_state(plot)

print("Plot type:", type(plot).__name__)
print("Plot handles keys:", list(plot.handles.keys()))
for k, v in plot.handles.items():
    if "legend" in k.lower():
        print(f"  handles['{k}']: {type(v).__name__} = {v}")

print("\nFigure type:", type(fig).__name__)
if hasattr(fig, "axes"):
    for i, ax in enumerate(fig.axes):
        print(f"  axes[{i}]: legend = {ax.get_legend()}")
        if ax.get_legend():
            print(f"    legend type: {type(ax.get_legend()).__name__}")
