#!/usr/bin/env python
import sys
import traceback

def run_test(name, func, output_file):
    try:
        func()
        output_file.write(f"PASS: {name}\n")
        return True
    except Exception as e:
        output_file.write(f"FAIL: {name}: {e}\n")
        output_file.write(traceback.format_exc())
        output_file.write("\n")
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
    assert "theme" not in opts.kwargs

def test_explicit_opts_override_theme():
    import holoviews as hv
    hv.extension("bokeh")
    
    hv.opts.defaults_theme("presentation")
    
    curve = hv.Curve([1, 2, 3]).opts(bgcolor="#ff0000")
    
    from holoviews.core.options import lookup_options
    opts = lookup_options(curve, "plot", "bokeh")
    
    assert opts.kwargs["bgcolor"] == "#ff0000"
    assert opts.kwargs.get("text_font_size") == "16pt"

def test_full_priority_chain():
    import holoviews as hv
    hv.extension("bokeh")
    
    hv.opts.defaults_theme("default")
    
    curve = hv.Curve([1, 2, 3]).opts(theme="dark", bgcolor="#ff0000")
    
    from holoviews.core.options import lookup_options
    
    with hv.opts.theme("presentation"):
        opts = lookup_options(curve, "plot", "bokeh")
        assert opts.kwargs["bgcolor"] == "#ff0000"
        assert opts.kwargs.get("text_font_size") == "12pt"

def test_object_theme_overrides_global():
    import holoviews as hv
    hv.extension("bokeh")
    
    hv.opts.defaults_theme("default")
    
    curve1 = hv.Curve([1, 2, 3]).opts(theme="dark")
    curve2 = hv.Curve([1, 2, 3])
    
    from holoviews.core.options import lookup_options
    
    opts1 = lookup_options(curve1, "plot", "bokeh")
    opts2 = lookup_options(curve2, "plot", "bokeh")
    
    assert opts1.kwargs.get("bgcolor") == "#222222"
    assert opts2.kwargs.get("bgcolor") == "#ffffff"

def test_context_theme_overrides_global():
    import holoviews as hv
    hv.extension("bokeh")
    
    hv.opts.defaults_theme("default")
    curve = hv.Curve([1, 2, 3])
    
    from holoviews.core.options import lookup_options
    
    with hv.opts.theme("dark"):
        opts = lookup_options(curve, "plot", "bokeh")
        assert opts.kwargs.get("bgcolor") == "#222222"
    
    opts2 = lookup_options(curve, "plot", "bokeh")
    assert opts2.kwargs.get("bgcolor") == "#ffffff"

def test_bokeh_legend_styles_mapped():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "bokeh", "plot")
    
    assert "legend_position" in opts
    assert "legend_opts" in opts
    assert "label_text_font_size" in opts["legend_opts"]

def test_bokeh_colorbar_styles_mapped():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "bokeh", "plot")
    
    assert "colorbar_opts" in opts
    assert "title_text_font_size" in opts["colorbar_opts"]

def test_bokeh_hover_styles_mapped():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "bokeh", "style")
    
    assert "hover_fill_color" in opts
    assert "hover_fill_alpha" in opts

def test_bokeh_toolbar_styles_mapped():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "bokeh", "plot")
    
    assert opts["toolbar"] == "above"
    assert opts["autohide_toolbar"] is True

def test_matplotlib_rcparams_mapped():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "matplotlib", "plot")
    
    assert "fig_rcparams" in opts
    assert opts["fig_rcparams"]["font.size"] == 16

def test_plotly_hover_styles_mapped():
    from holoviews.core.theme import get_theme, _theme_to_options
    theme = get_theme("presentation")
    opts = _theme_to_options(theme, "plotly", "style")
    
    assert "hoverlabel_bgcolor" in opts
    assert "hoverlabel_font_size" in opts

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
    
    assert merged.kwargs["bgcolor"] == "#ff0000"
    assert merged.kwargs["text_font"] == "Helvetica"

def test_builtin_themes_have_complete_styles():
    from holoviews.core.theme import list_themes, get_theme
    
    themes = list_themes()
    assert len(themes) >= 5
    
    for theme_name in ["default", "presentation", "dark", "minimal", "ggplot"]:
        theme = get_theme(theme_name)
        for backend in ["bokeh", "matplotlib", "plotly"]:
            styles = theme.get_styles(backend)
            assert styles.font
            assert styles.background
            assert styles.grid
            assert styles.legend
            assert styles.toolbar

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
    
    assert "hover_fill_color" in opts.kwargs
    assert "grid_line_color" in opts.kwargs

def test_theme_parameter_not_in_style_options():
    import holoviews as hv
    hv.extension("bokeh")
    
    curve = hv.Curve([1, 2, 3]).opts(theme="dark")
    
    from holoviews.core.options import lookup_options
    opts = lookup_options(curve, "style", "bokeh")
    
    assert "theme" not in opts.kwargs

def test_nested_context_properly_stacked():
    import holoviews as hv
    hv.extension("bokeh")
    
    hv.opts.defaults_theme(None)
    curve = hv.Curve([1, 2, 3])
    
    from holoviews.core.options import lookup_options
    
    with hv.opts.theme("default"):
        with hv.opts.theme("dark"):
            opts = lookup_options(curve, "plot", "bokeh")
            assert opts.kwargs.get("bgcolor") == "#222222"
        
        opts2 = lookup_options(curve, "plot", "bokeh")
        assert opts2.kwargs.get("bgcolor") == "#ffffff"
    
    assert hv.opts.current_theme() is None

if __name__ == "__main__":
    with open("/Users/pkcha/holoviews/test_results.txt", "w") as f:
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
            results.append(run_test(name, func, f))
        
        f.write("\n")
        passed = sum(results)
        total = len(results)
        f.write(f"Results: {passed}/{total} tests passed\n")
        
        if all(results):
            f.write("\nAll tests passed!\n")
        else:
            f.write(f"\n{total - passed} tests failed\n")
    
    print("Tests completed. Results written to test_results.txt")
    print(f"Results: {passed}/{total} tests passed")
    sys.exit(0 if all(results) else 1)
