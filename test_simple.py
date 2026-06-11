import holoviews as hv
from holoviews.core.theme import get_theme, _theme_to_options

print("Available themes:", hv.opts.list_themes())

theme = get_theme("presentation")
print("Presentation theme exists:", theme is not None)

opts = _theme_to_options(theme, "bokeh", "plot")
print("Bokeh plot opts keys:", list(opts.keys())[:10])

opts_style = _theme_to_options(theme, "bokeh", "style")
print("Bokeh style opts keys:", list(opts_style.keys())[:10])

print("\n--- Testing theme parameter filter ---")
hv.extension("bokeh")
curve = hv.Curve([1, 2, 3]).opts(theme="dark", bgcolor="#ff0000")

from holoviews.core.options import lookup_options
opts = lookup_options(curve, "plot", "bokeh")
print("Plot options keys:", list(opts.kwargs.keys()))
print("'theme' in plot options:", "theme" in opts.kwargs)
print("'bgcolor' value:", opts.kwargs.get("bgcolor"))

print("\n--- Testing style options ---")
opts_style = lookup_options(curve, "style", "bokeh")
print("Style options keys:", list(opts_style.kwargs.keys())[:10])
print("'theme' in style options:", "theme" in opts_style.kwargs)

print("\n--- Testing priority ---")
hv.opts.defaults_theme("presentation")
curve2 = hv.Curve([1, 2, 3]).opts(bgcolor="#00ff00")
opts2 = lookup_options(curve2, "plot", "bokeh")
print("bgcolor (should be #00ff00):", opts2.kwargs.get("bgcolor"))
print("text_font_size (should be 16pt):", opts2.kwargs.get("text_font_size"))
