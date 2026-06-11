import holoviews as hv
import numpy as np

hv.extension("bokeh")

from holoviews.core.theme import get_theme, get_active_theme, list_themes
from holoviews.core.options import lookup_options

print("=== 列出所有主题 ===")
print(list_themes())

print("\n=== 获取默认主题 ===")
theme = get_theme("default")
print(f"主题名: {theme.name}")
print(f"样式: {theme.get_styles('bokeh')}")

print("\n=== 测试全局主题设置 ===")
hv.opts.defaults_theme("dark")
print(f"当前活动主题: {get_active_theme().name}")

print("\n=== 测试 Curve 元素的主题选项 ===")
curve = hv.Curve(np.random.randn(10))
plot_opts = lookup_options(curve, "plot", "bokeh")
print(f"Plot options keys: {list(plot_opts.kwargs.keys())}")
print(f"Has theme in plot opts: {'theme' in plot_opts.kwargs}")

style_opts = lookup_options(curve, "style", "bokeh")
print(f"Style options keys: {list(style_opts.kwargs.keys())}")

print("\n=== 测试单对象主题覆盖 ===")
curve2 = hv.Curve(np.random.randn(10)).opts(theme="presentation")
plot_opts2 = lookup_options(curve2, "plot", "bokeh")
print(f"Plot options keys: {list(plot_opts2.kwargs.keys())}")
print(f"Has theme in plot opts: {'theme' in plot_opts2.kwargs}")

print("\n=== 测试上下文管理器 ===")
with hv.opts.theme("ggplot"):
    print(f"上下文中的活动主题: {get_active_theme().name}")
print(f"上下文后的活动主题: {get_active_theme().name}")

print("\n=== 测试用户显式选项覆盖主题 ===")
curve3 = hv.Curve(np.random.randn(10)).opts(bgcolor="red", backend="bokeh")
plot_opts3 = lookup_options(curve3, "plot", "bokeh")
print(f"bgcolor: {plot_opts3.kwargs.get('bgcolor')}")

print("\n=== 测试完成 ===")
