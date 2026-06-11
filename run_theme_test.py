import sys
import traceback

output = []

def log(msg):
    output.append(str(msg))
    print(msg)

try:
    import holoviews as hv
    import numpy as np

    log("=== 测试主题系统集成 ===")

    from holoviews.core.theme import (
        get_theme, get_active_theme, list_themes,
        set_default_theme, theme_context, theme_registry
    )
    from holoviews.core.options import lookup_options, Store

    log("\n1. 列出所有主题")
    themes = list_themes()
    log(f"   主题列表: {themes}")
    log(f"   主题数量: {len(themes)}")

    log("\n2. 测试默认主题")
    default_theme = get_theme("default")
    log(f"   主题名: {default_theme.name}")
    log(f"   描述: {default_theme.description}")
    bokeh_styles = default_theme.get_styles("bokeh")
    log(f"   Bokeh 字体样式: {bokeh_styles.font}")
    log(f"   Bokeh 网格样式: {bokeh_styles.grid}")
    log(f"   Bokeh 背景样式: {bokeh_styles.background}")

    log("\n3. 测试全局主题设置")
    set_default_theme("dark")
    log(f"   设置全局主题后，当前活动主题: {get_active_theme().name}")

    log("\n4. 测试上下文管理器")
    log(f"   上下文前: {get_active_theme().name}")
    with theme_context("ggplot"):
        log(f"   上下文中: {get_active_theme().name}")
    log(f"   上下文后: {get_active_theme().name}")

    log("\n5. 测试 Bokeh 后端 plot 选项映射")
    hv.extension("bokeh")
    curve = hv.Curve(np.random.randn(10))
    plot_opts = lookup_options(curve, "plot", "bokeh")
    log(f"   Plot 选项数量: {len(plot_opts.kwargs)}")
    log(f"   Plot 选项键: {sorted(plot_opts.kwargs.keys())}")
    log(f"   包含 theme: {'theme' in plot_opts.kwargs}")

    style_opts = lookup_options(curve, "style", "bokeh")
    log(f"   Style 选项数量: {len(style_opts.kwargs)}")
    log(f"   包含 theme: {'theme' in style_opts.kwargs}")

    log("\n6. 测试单对象主题覆盖")
    curve2 = hv.Curve(np.random.randn(10)).opts(theme="presentation")
    plot_opts2 = lookup_options(curve2, "plot", "bokeh")
    log(f"   Plot 选项键: {sorted(plot_opts2.kwargs.keys())}")
    log(f"   包含 theme: {'theme' in plot_opts2.kwargs}")

    log("\n7. 测试用户显式选项覆盖主题")
    curve3 = hv.Curve(np.random.randn(10)).opts(bgcolor="#ff0000", backend="bokeh")
    plot_opts3 = lookup_options(curve3, "plot", "bokeh")
    log(f"   bgcolor 值: {plot_opts3.kwargs.get('bgcolor')}")
    log(f"   是否是用户设置的红色: {plot_opts3.kwargs.get('bgcolor') == '#ff0000'}")

    log("\n8. 测试 dark 主题的 Bokeh 样式")
    dark_theme = get_theme("dark")
    dark_bokeh = dark_theme.get_styles("bokeh")
    log(f"   背景色: {dark_bokeh.background.get('color')}")
    log(f"   字体颜色: {dark_bokeh.font.get('color')}")

    log("\n9. 验证 toolbar 样式")
    log(f"   default 主题 toolbar: {default_theme.get_styles('bokeh').toolbar}")
    log(f"   presentation 主题 toolbar: {get_theme('presentation').get_styles('bokeh').toolbar}")

    log("\n10. 验证 legend 样式")
    log(f"   default 主题 legend: {default_theme.get_styles('bokeh').legend}")

    log("\n11. 验证 colorbar 样式")
    log(f"   default 主题 colorbar: {default_theme.get_styles('bokeh').colorbar}")

    log("\n12. 验证 hover 样式")
    log(f"   default 主题 hover: {default_theme.get_styles('bokeh').hover}")

    log("\n=== 所有测试通过 ===")

except Exception as e:
    log(f"\n错误: {e}")
    log(traceback.format_exc())

# 写入文件
with open("/Users/pkcha/holoviews/test_output.txt", "w") as f:
    f.write("\n".join(output))

print("测试完成，结果已写入 test_output.txt")
