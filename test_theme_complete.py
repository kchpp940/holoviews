#!/usr/bin/env python
"""Complete test for theme system integration"""
import sys

def run_test(name, func):
    try:
        func()
        print(f"✓ {name}")
        return True
    except Exception as e:
        print(f"✗ {name}: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_basic_imports():
    import holoviews as hv
    from holoviews.core.theme import (
        Theme, ThemeStyles, ThemeRegistry, ThemeState,
        list_themes, get_theme, register_theme,
        set_default_theme, theme_context, get_active_theme,
        _theme_to_options, _merge_options_with_theme,
    )
    assert hv.Theme is Theme
    assert hv.ThemeStyles is ThemeStyles
    assert hv.list_themes is list_themes

def test_theme_parameter_not_leaked():
    import holoviews as hv
    hv.extension("bokeh")
    
    curve = hv.Curve([1, 2, 3]).opts(theme="dark", bgcolor="#ff0000")
    
    from holoviews.core.options import lookup_options
    opts = lookup_options(curve, "plot", "bokeh")
    assert "theme" not in opts.kwargs, f"'theme' should not be in plot options, but found: {list(opts.kwargs.keys())}"

def test_explicit_opts_override_theme():
    import holoviews as hv
    hv.extension("bokeh")
    
    hv.opts.defaults_theme("presentation")
    
    curve = hv.Curve([1, 2, 3]).opts(bgcolor="#ff0000")
    
    from holoviews.core.options import lookup_options
    opts = lookup_options(curve, "plot", "bokeh")
    
    assert opts.kwargs["bgcolor"] == "#ff0000", "Explicit bgcolor should override theme"
    assert opts.kwargs.get("text_font_size") == "16pt", "Theme font size should be applied"

def test_full_priority_chain():
    import holoviews as hv
    hv.extension("bokeh")
    
    hv.opts.defaults_theme("default")
    
    curve = hv.Curve([1, 2, 3]).opts(theme="dark", bgcolor="#ff0000")
    
    from holoviews.core.options import lookup_options
    
    with hv.opts.theme("presentation"):
        opts = lookup_options(curve, "plot", "bokeh")
        assert opts.kwargs["bgcolor"] == "#ff0000", "Explicit opts should have highest priority"
        assert opts.kwargs.get("text_font_size") == "12pt", "Object theme should override context and global"

def test_object_theme_overrides_global():
    import holoviews as hv
    hv.extension("bokeh")
    
    hv.opts.defaults_theme("default")
    
    curve1 = hv.Curve([1, 2, 3]).opts(theme="dark")
    curve2 = hv.Curve([1, 2, 3])
    
    from holoviews.core.options import lookup_options
    
    opts1 = lookup_options(curve1, "plot", "bokeh")
    opts2 = lookup_options(curve2, "plot", "bokeh")
    
    assert opts1.kwargs.get("bgcolor") == "#222222", "Object theme should apply"
    assert opts2.kwargs.get("bgcolor") == "#ffffff", "Global theme should apply"

def test_context_theme_overrides_global():
    import holoviews as hv
    hv.extension("bokeh")
    
    hv.opts.defaults_theme("default")
    curve = hv.Curve([1, 2, 3])
    
    from holoviews.core.options import lookup_options
    
    with hv.opts.theme("dark"):
        opts = lookup_options(curve, "plot", "bokeh")
        assert opts.kwargs.get("bgcolor") == "#222222", "Context theme should override global"
    
    opts2 = lookup_options(curve, "plot", "bokeh")
    assert opts2.kwargs.get("bgcolor") == "#ffffff", "Global theme should restore after context"

def test_bokeh_legend_styles_mapped():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "bokeh", "plot")
    
    assert "legend_position" in opts, "legend_position should be mapped"
    assert "legend_opts" in opts, "legend_opts should be mapped"
    assert "label_text_font_size" in opts["legend_opts"], "label_text_font_size should be in legend_opts"

def test_bokeh_colorbar_styles_mapped():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "bokeh", "plot")
    
    assert "colorbar_opts" in opts, "colorbar_opts should be mapped"
    assert "title_text_font_size" in opts["colorbar_opts"], "title_text_font_size should be in colorbar_opts"

def test_bokeh_hover_styles_mapped():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "bokeh", "style")
    
    assert "hover_fill_color" in opts, "hover_fill_color should be mapped"
    assert "hover_fill_alpha" in opts, "hover_fill_alpha should be mapped"

def test_bokeh_toolbar_styles_mapped():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "bokeh", "plot")
    
    assert opts["toolbar"] == "above", "toolbar position should be mapped"
    assert opts["autohide_toolbar"] is True, "autohide_toolbar should be mapped"

def test_matplotlib_rcparams_mapped():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "matplotlib", "plot")
    
    assert "fig_rcparams" in opts, "fig_rcparams should be mapped"
    assert opts["fig_rcparams"]["font.size"] == 16, "font.size should be mapped"

def test_plotly_hover_styles_mapped():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "plotly", "style")
    
    assert "hoverlabel_bgcolor" in opts, "hoverlabel_bgcolor should be mapped"
    assert "hoverlabel_font_size" in opts, "hoverlabel_font_size should be mapped"

def test_merge_options_priority():
    from holoviews.core.options import Options
    from holoviews.core.theme import (
        Theme, ThemeStyles, _merge_options_with_theme
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

def test_builtin_themes_have_complete_styles():
    from holoviews.core.theme import list_themes, get_theme
    
    themes = list_themes()
    assert len(themes) >= 5, "Should have at least 5 builtin themes"
    
    for theme_name in ["default", "presentation", "dark", "minimal", "ggplot"]:
        theme = get_theme(theme_name)
        for backend in ["bokeh", "matplotlib", "plotly"]:
            styles = theme.get_styles(backend)
            assert styles.font, f"{theme_name} should have font styles for {backend}"
            assert styles.background, f"{theme_name} should have background styles for {backend}"
            assert styles.grid, f"{theme_name} should have grid styles for {backend}"
            assert styles.legend, f"{theme_name} should have legend styles for {backend}"
            assert styles.toolbar, f"{theme_name} should have toolbar styles for {backend}"

def test_dark_theme_contrast():
    from holoviews.core.theme import get_theme
    theme = get_theme("dark")
    
    bokeh_styles = theme.get_styles("bokeh")
    assert bokeh_styles.background["color"] == "#222222"
    assert bokeh_styles.font["color"] == "#ffffff"
    assert bokeh_styles.grid["color"] == "#404040"
    
    plotly_styles = theme.get_styles("plotly")
    assert plotly_styles.background["color"] == "#222222"
    assert plotly_styles.font["color"] == "#ffffff"

def test_minimal_theme_minimal_decorations():
    from holoviews.core.theme import get_theme
    theme = get_theme("minimal")
    
    bokeh_styles = theme.get_styles("bokeh")
    assert bokeh_styles.grid["show"] is False
    assert bokeh_styles.toolbar["show"] is False
    
    mpl_styles = theme.get_styles("matplotlib")
    assert mpl_styles.grid["show"] is False
    assert mpl_styles.toolbar["show"] is False

def test_style_options_also_merged():
    import holoviews as hv
    hv.extension("bokeh")
    
    hv.opts.defaults_theme("presentation")
    curve = hv.Curve([1, 2, 3])
    
    from holoviews.core.options import lookup_options
    opts = lookup_options(curve, "style", "bokeh")
    
    assert "hover_fill_color" in opts.kwargs, "Style options should include hover styles"
    assert "grid_line_color" in opts.kwargs, "Style options should include grid styles"

def test_theme_parameter_not_in_style_options():
    import holoviews as hv
    hv.extension("bokeh")
    
    curve = hv.Curve([1, 2, 3]).opts(theme="dark")
    
    from holoviews.core.options import lookup_options
    opts = lookup_options(curve, "style", "bokeh")
    
    assert "theme" not in opts.kwargs, "'theme' should not be in style options"

def test_nested_context_properly_stacked():
    import holoviews as hv
    hv.extension("bokeh")
    
    hv.opts.defaults_theme(None)
    curve = hv.Curve([1, 2, 3])
    
    from holoviews.core.options import lookup_options
    
    with hv.opts.theme("default"):
        with hv.opts.theme("dark"):
            opts = lookup_options(curve, "plot", "bokeh")
            assert opts.kwargs.get("bgcolor") == "#222222", "Inner context should apply"
        
        opts2 = lookup_options(curve, "plot", "bokeh")
        assert opts2.kwargs.get("bgcolor") == "#ffffff", "Outer context should restore"
    
    assert hv.opts.current_theme() is None, "Global should restore"

if __name__ == "__main__":
    tests = [
        ("Basic imports", test_basic_imports),
        ("Theme parameter not leaked to backend", test_theme_parameter_not_leaked),
        ("Explicit opts override theme", test_explicit_opts_override_theme),
        ("Full priority chain", test_full_priority_chain),
        ("Object theme overrides global", test_object_theme_overrides_global),
        ("Context theme overrides global", test_context_theme_overrides_global),
        ("Bokeh legend styles mapped", test_bokeh_legend_styles_mapped),
        ("Bokeh colorbar styles mapped", test_bokeh_colorbar_styles_mapped),
        ("Bokeh hover styles mapped", test_bokeh_hover_styles_mapped),
        ("Bokeh toolbar styles mapped", test_bokeh_toolbar_styles_mapped),
        ("Matplotlib rcparams mapped", test_matplotlib_rcparams_mapped),
        ("Plotly hover styles mapped", test_plotly_hover_styles_mapped),
        ("Merge options priority", test_merge_options_priority),
        ("Builtin themes have complete styles", test_builtin_themes_have_complete_styles),
        ("Dark theme contrast colors", test_dark_theme_contrast),
        ("Minimal theme minimal decorations", test_minimal_theme_minimal_decorations),
        ("Style options also merged", test_style_options_also_merged),
        ("Theme parameter not in style options", test_theme_parameter_not_in_style_options),
        ("Nested context properly stacked", test_nested_context_properly_stacked),
    ]
    
    results = []
    for name, func in tests:
        results.append(run_test(name, func))
    
    print()
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    
    if all(results):
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print(f"\n✗ {total - passed} tests failed")
        sys.exit(1)
