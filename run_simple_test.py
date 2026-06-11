import sys
import traceback

passed = 0
failed = 0
results = []

def test(name, func):
    global passed, failed
    try:
        func()
        results.append(("PASS", name, ""))
        passed += 1
    except Exception as e:
        results.append(("FAIL", name, str(e) + "\n" + traceback.format_exc()))
        failed += 1

# Test 1
def t1():
    import holoviews as hv
    from holoviews.core.theme import (
        Theme, ThemeStyles, ThemeRegistry, ThemeState,
        list_themes, get_theme, _theme_to_options,
        _merge_options_with_theme,
    )
    assert hv.list_themes is list_themes

test("Basic imports", t1)

# Test 2
def t2():
    from holoviews.core.theme import list_themes
    themes = list_themes()
    assert isinstance(themes, list)
    assert len(themes) >= 5
    for t in ["default", "presentation", "dark", "minimal", "ggplot"]:
        assert t in themes

test("List builtin themes", t2)

# Test 3
def t3():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "bokeh", "plot")
    assert isinstance(opts, dict)

test("Bokeh plot options mapping", t3)

# Test 4
def t4():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "bokeh", "style")
    assert isinstance(opts, dict)

test("Bokeh style options mapping", t4)

# Test 5
def t5():
    from holoviews.core.options import Options
    from holoviews.core.theme import (
        Theme, ThemeStyles, _merge_options_with_theme,
    )
    styles = ThemeStyles(
        font={"family": "Helvetica", "size": "12pt"},
        background={"color": "#ffffff"},
    )
    theme = Theme("test", {"bokeh": styles})
    user_opts = Options(bgcolor="#ff0000")
    merged = _merge_options_with_theme(user_opts, theme, "bokeh", "plot")
    assert merged.kwargs["bgcolor"] == "#ff0000"
    assert merged.kwargs["text_font"] == "Helvetica"

test("Merge options priority", t5)

# Test 6: Theme not leaked
def t6():
    import holoviews as hv
    hv.extension("bokeh")
    hv.opts.defaults_theme("presentation")
    curve = hv.Curve([1, 2, 3, 4, 5]).opts(theme="dark")
    opts = hv.Store.lookup_options("bokeh", curve, "plot")
    assert "theme" not in opts.kwargs
    hv.opts.defaults_theme(None)

test("Theme not leaked to plot options", t6)

# Test 7: Theme not leaked in style
def t7():
    import holoviews as hv
    hv.extension("bokeh")
    curve = hv.Curve([1, 2, 3]).opts(theme="dark")
    opts = hv.Store.lookup_options("bokeh", curve, "style")
    assert "theme" not in opts.kwargs

test("Theme not leaked to style options", t7)

# Test 8: Explicit opts override
def t8():
    import holoviews as hv
    hv.extension("bokeh")
    hv.opts.defaults_theme("presentation")
    curve = hv.Curve([1, 2, 3]).opts(bgcolor="#00ff00")
    opts = hv.Store.lookup_options("bokeh", curve, "plot")
    assert opts.kwargs["bgcolor"] == "#00ff00"
    hv.opts.defaults_theme(None)

test("Explicit opts override theme", t8)

# Test 9: Context manager
def t9():
    import holoviews as hv
    hv.extension("bokeh")
    assert hv.opts.current_theme() is None
    with hv.opts.theme("dark"):
        assert hv.opts.current_theme().name == "dark"
    assert hv.opts.current_theme() is None

test("Context manager", t9)

# Test 10: Per-object theme override
def t10():
    import holoviews as hv
    hv.extension("bokeh")
    hv.opts.defaults_theme("default")
    curve1 = hv.Curve([1, 2, 3]).opts(theme="dark")
    curve2 = hv.Curve([1, 2, 3])
    opts1 = hv.Store.lookup_options("bokeh", curve1, "plot")
    opts2 = hv.Store.lookup_options("bokeh", curve2, "plot")
    assert opts1.kwargs.get("bgcolor") == "#222222"
    hv.opts.defaults_theme(None)

test("Per-object theme override", t10)

# Write results
with open("/Users/pkcha/holoviews/test_output.txt", "w") as f:
    for status, name, detail in results:
        f.write(f"{status}: {name}\n")
        if detail:
            f.write(f"  {detail}\n")
    f.write(f"\nTotal: {passed}/{passed + failed} passed\n")

print("Done")
