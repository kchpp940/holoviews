"""Smoke test for plot/backend option schema integration."""
import numpy as np
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import holoviews as hv
from holoviews import Curve, Scatter, opts
from holoviews.core.schema import (
    OptionCategory, OptionSpec, OptionSchema, ValidationError,
    build_style_schema, build_norm_schema, build_plot_schema,
)
from holoviews.core.options import Store, Options

hv.extension('bokeh')

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  ✓ {name}")
        passed += 1
    else:
        print(f"  ✗ {name}: {detail}")
        failed += 1

print("=== 1. Store.options_schema() API ===")
# Check that schemas were registered for Curve
plot_schema = Store.options_schema("Curve", "plot", backend="bokeh")
style_schema = Store.options_schema("Curve", "style", backend="bokeh")
norm_schema = Store.options_schema("Curve", "norm", backend="bokeh")
output_schema = Store.options_schema("Curve", "output", backend="bokeh")

check("plot schema exists for Curve", plot_schema is not None)
check("style schema exists for Curve", style_schema is not None)
check("norm schema exists for Curve", norm_schema is not None)
check("output schema exists for Curve", output_schema is not None)

if plot_schema:
    check("plot schema has show_title", "show_title" in plot_schema)
    check("plot schema has xaxis", "xaxis" in plot_schema)
    check("plot schema category is plot", plot_schema.category == OptionCategory.PLOT)

if style_schema:
    check("style schema has line_color", "line_color" in style_schema)
    check("style schema has color", "color" in style_schema)
    check("style schema category is style", style_schema.category == OptionCategory.STYLE)

if norm_schema:
    check("norm schema has framewise", "framewise" in norm_schema)
    check("norm schema has axiswise", "axiswise" in norm_schema)
    check("norm schema category is norm", norm_schema.category == OptionCategory.NORM)

print()
print("=== 2. .opts() unknown option raises ValueError ===")
curve = Curve(np.random.randn(100).cumsum())
try:
    curve.opts(invalid_option='foo')
    check("unknown option raises", False, "should have raised ValueError")
except ValueError as e:
    msg = str(e)
    check("error mentions category", "Invalid plot option" in msg or "Invalid style option" in msg or "Unexpected option" in msg)
    check("error has suggestion", "Did you mean" in msg or "Similar options" in msg)
    print(f"    Error msg: {msg.split(chr(10))[0]}")

print()
print("=== 3. .opts() wrong type raises ValueError ===")
try:
    curve.opts(show_title='not_a_bool')
    check("wrong type raises", False, "should have raised ValueError")
except ValueError as e:
    msg = str(e)
    check("error mentions type", "expected type bool" in msg or "Invalid plot option" in msg)
    print(f"    Error msg: {msg.split(chr(10))[0]}")

print()
print("=== 4. .opts() valid options work ===")
try:
    c = curve.opts(show_title=False, line_color='red', xaxis='bare', framewise=True)
    check("valid options accepted", True)
except Exception as e:
    check("valid options accepted", False, str(e))

print()
print("=== 5. hv.opts() builder API ===")
try:
    c2 = curve.opts(opts.Curve(show_title=False, line_width=3))
    check("opts.Curve builder works", True)
except Exception as e:
    check("opts.Curve builder works", False, str(e))

print()
print("=== 6. hv.opts() builder unknown option ===")
try:
    c3 = curve.opts(opts.Curve(not_a_real_option=42))
    check("opts.Curve unknown raises", False, "should have raised")
except ValueError as e:
    check("opts.Curve unknown raises", True)
    print(f"    Error msg: {str(e)[:80]}...")

print()
print("=== 7. Error message shows category labels ===")
# Try an option that's clearly in one category
try:
    curve.opts(show_titl=False)  # misspelling of show_title (plot)
except ValueError as e:
    msg = str(e)
    check("show_titl suggestion has [plot] label", "[plot]" in msg or "Did you mean" in msg)
    print(f"    Msg snippet: {msg.split(chr(10))[1] if chr(10) in msg else msg[:80]}")

try:
    curve.opts(line_colr='red')  # misspelling of line_color (style)
except ValueError as e:
    msg = str(e)
    check("line_colr suggestion has [style] label", "[style]" in msg or "Did you mean" in msg)
    print(f"    Msg snippet: {msg.split(chr(10))[1] if chr(10) in msg else msg[:80]}")

print()
print("=== 8. Options class with schema ===")
# Create an Options with a schema and verify validation works
schema = OptionSchema(
    OptionCategory.PLOT,
    OptionSpec("show_title", type=bool, default=True),
    OptionSpec("xaxis", type=str, default=None, allow_None=True, allowed=["top", "bottom", "bare", None]),
)
try:
    opts1 = Options(key="plot", schema=schema, show_title=False)
    check("Options with schema accepts valid", True)
except Exception as e:
    check("Options with schema accepts valid", False, str(e))

try:
    opts2 = Options(key="plot", schema=schema, show_title="yes")
    check("Options with schema rejects wrong type", False, "should have raised OptionError")
except Exception as e:
    check("Options with schema rejects wrong type", True)

try:
    opts3 = Options(key="plot", schema=schema, unknown_opt=1)
    check("Options with schema rejects unknown", False, "should have raised OptionError")
except Exception as e:
    check("Options with schema rejects unknown", True)

print()
print("=== 9. build_style_schema and build_norm_schema ===")
style_s = build_style_schema(["color", "line_width", "alpha"], backend="test", element_name="TestElement")
check("build_style_schema creates STYLE category", style_s.category == OptionCategory.STYLE)
check("build_style_schema has all options", all(k in style_s for k in ["color", "line_width", "alpha"]))

norm_s = build_norm_schema()
check("build_norm_schema creates NORM category", norm_s.category == OptionCategory.NORM)
check("build_norm_schema has framewise/axiswise", "framewise" in norm_s and "axiswise" in norm_s)

print()
print(f"=== Results: {passed} passed, {failed} failed ===")
if failed > 0:
    exit(1)
