#!/usr/bin/env python
"""Quick test for theme system"""
import sys
import traceback

passed = 0
failed = 0

def test(name, func):
    global passed, failed
    try:
        func()
        print(f"PASS: {name}")
        passed += 1
    except Exception as e:
        print(f"FAIL: {name}: {e}")
        traceback.print_exc()
        failed += 1

# Test 1: Basic imports
def test_imports():
    import holoviews as hv
    from holoviews.core.theme import (
        Theme, ThemeStyles, ThemeRegistry, ThemeState,
        list_themes, get_theme, _theme_to_options,
        _merge_options_with_theme,
    )
    assert hv.list_themes is list_themes

test("Basic imports", test_imports)

# Test 2: List builtin themes
def test_list_themes():
    from holoviews.core.theme import list_themes
    themes = list_themes()
    assert isinstance(themes, list)
    assert len(themes) >= 5
    for t in ["default", "presentation", "dark", "minimal", "ggplot"]:
        assert t in themes

test("List builtin themes", test_list_themes)

# Test 3: Bokeh plot options mapping
def test_bokeh_plot_opts():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "bokeh", "plot")
    
    # Check that common options exist
    assert "bgcolor" in opts or "text_font_size" in opts or "toolbar" in opts
    print(f"  Bokeh plot opts keys: {list(opts.keys())[:15]}...")

test("Bokeh plot options mapping", test_bokeh_plot_opts)

# Test 4: Bokeh style options mapping
def test_bokeh_style_opts():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "bokeh", "style")
    print(f"  Bokeh style opts keys: {list(opts.keys())[:15]}...")

test("Bokeh style options mapping", test_bokeh_style_opts)

# Test 5: Matplotlib plot options mapping
def test_mpl_plot_opts():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "matplotlib", "plot")
    assert "fig_rcparams" in opts
    print(f"  MPL plot opts keys: {list(opts.keys())}")
    print(f"  fig_rcparams keys: {list(opts.get('fig_rcparams', {}).keys())[:10]}...")

test("Matplotlib plot options mapping", test_mpl_plot_opts)

# Test 6: Plotly plot options mapping
def test_plotly_plot_opts():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "plotly", "plot")
    print(f"  Plotly plot opts keys: {list(opts.keys())}")

test("Plotly plot options mapping", test_plotly_plot_opts)

# Test 7: Merge options with theme - user opts should win
def test_merge_priority():
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
    
    assert merged.kwargs["bgcolor"] == "#ff0000", "User opts should override theme"
    assert merged.kwargs["text_font"] == "Helvetica", "Theme defaults should apply"

test("Merge options priority", test_merge_priority)

# Test 8: Theme with Bokeh extension
def test_theme_with_bokeh():
    import holoviews as hv
    hv.extension("bokeh")
    
    hv.opts.defaults_theme("presentation")
    curve = hv.Curve([1, 2, 3, 4, 5])
    
    opts = hv.Store.lookup_options("bokeh", curve, "plot")
    print(f"  Plot opts from Store: {list(opts.kwargs.keys())[:15]}...")
    
    # theme should NOT be in kwargs
    assert "theme" not in opts.kwargs, "theme should not leak to plot options"
    
    hv.opts.defaults_theme(None)

test("Theme with Bokeh extension", test_theme_with_bokeh)

# Test 9: Per-object theme override
def test_per_object_theme():
    import holoviews as hv
    hv.extension("bokeh")
    
    hv.opts.defaults_theme("default")
    curve1 = hv.Curve([1, 2, 3]).opts(theme="dark")
    curve2 = hv.Curve([1, 2, 3])
    
    opts1 = hv.Store.lookup_options("bokeh", curve1, "plot")
    opts2 = hv.Store.lookup_options("bokeh", curve2, "plot")
    
    assert "theme" not in opts1.kwargs
    assert "theme" not in opts2.kwargs
    
    print(f"  curve1 bgcolor: {opts1.kwargs.get('bgcolor')}")
    print(f"  curve2 bgcolor: {opts2.kwargs.get('bgcolor')}")
    
    hv.opts.defaults_theme(None)

test("Per-object theme override", test_per_object_theme)

# Test 10: Explicit opts override theme
def test_explicit_opts_override():
    import holoviews as hv
    hv.extension("bokeh")
    
    hv.opts.defaults_theme("presentation")
    curve = hv.Curve([1, 2, 3]).opts(bgcolor="#00ff00")
    
    opts = hv.Store.lookup_options("bokeh", curve, "plot")
    
    assert opts.kwargs["bgcolor"] == "#00ff00"
    print(f"  bgcolor (should be #00ff00): {opts.kwargs.get('bgcolor')}")
    
    hv.opts.defaults_theme(None)

test("Explicit opts override theme", test_explicit_opts_override)

# Test 11: Context manager
def test_context_manager():
    import holoviews as hv
    hv.extension("bokeh")
    
    assert hv.opts.current_theme() is None
    
    with hv.opts.theme("dark"):
        assert hv.opts.current_theme().name == "dark"
        curve = hv.Curve([1, 2, 3])
        opts = hv.Store.lookup_options("bokeh", curve, "plot")
        print(f"  Context theme bgcolor: {opts.kwargs.get('bgcolor')}")
    
    assert hv.opts.current_theme() is None

test("Context manager", test_context_manager)

# Test 12: Style options also merged
def test_style_opts_merged():
    import holoviews as hv
    hv.extension("bokeh")
    
    hv.opts.defaults_theme("presentation")
    curve = hv.Curve([1, 2, 3])
    
    opts = hv.Store.lookup_options("bokeh", curve, "style")
    print(f"  Style opts keys: {list(opts.kwargs.keys())[:15]}...")
    
    assert "theme" not in opts.kwargs
    
    hv.opts.defaults_theme(None)

test("Style options also merged", test_style_opts_merged)

# Summary
print(f"\n{'='*50}")
print(f"Results: {passed}/{passed + failed} tests passed")
print(f"{'='*50}")

if failed > 0:
    sys.exit(1)
