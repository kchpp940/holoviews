from __future__ import annotations

import pytest

import holoviews as hv
from holoviews.core.theme import (
    Theme,
    ThemeRegistry,
    ThemeState,
    ThemeStyles,
    get_active_theme,
    get_default_theme,
    get_theme,
    list_themes,
    register_theme,
    set_default_theme,
    theme_context,
    theme_registry,
    theme_state,
    unregister_theme,
)


class TestThemeStyles:
    def test_default_styles(self):
        styles = ThemeStyles()
        assert styles.font == {}
        assert styles.grid == {}
        assert styles.background == {}
        assert styles.legend == {}
        assert styles.toolbar == {}
        assert styles.colorbar == {}
        assert styles.hover == {}

    def test_styles_initialization(self):
        styles = ThemeStyles(
            font={"family": "Arial", "size": 12},
            grid={"show": True, "color": "#000000"},
        )
        assert styles.font == {"family": "Arial", "size": 12}
        assert styles.grid == {"show": True, "color": "#000000"}

    def test_styles_merge(self):
        styles1 = ThemeStyles(
            font={"family": "Arial", "size": 12},
            grid={"show": True},
        )
        styles2 = ThemeStyles(
            font={"size": 14, "color": "red"},
            background={"color": "white"},
        )
        merged = styles1.merge(styles2)
        assert merged.font == {"family": "Arial", "size": 14, "color": "red"}
        assert merged.grid == {"show": True}
        assert merged.background == {"color": "white"}

    def test_styles_to_dict(self):
        styles = ThemeStyles(
            font={"family": "Arial"},
            grid={"show": True},
        )
        d = styles.to_dict()
        assert d["font"] == {"family": "Arial"}
        assert d["grid"] == {"show": True}


class TestTheme:
    def test_theme_initialization(self):
        theme = Theme("test_theme")
        assert theme.name == "test_theme"
        assert theme.description == ""

    def test_theme_with_styles(self):
        styles = ThemeStyles(font={"family": "Arial"})
        theme = Theme(
            "test_theme",
            styles={"bokeh": styles},
            description="Test theme",
        )
        assert theme.name == "test_theme"
        assert theme.description == "Test theme"
        assert theme.get_styles("bokeh") == styles
        assert theme.get_styles("matplotlib") == ThemeStyles()

    def test_theme_set_styles(self):
        theme = Theme("test_theme")
        styles = ThemeStyles(font={"family": "Arial"})
        theme.set_styles("bokeh", styles)
        assert theme.get_styles("bokeh") == styles

    def test_theme_update_styles(self):
        theme = Theme("test_theme")
        styles1 = ThemeStyles(font={"family": "Arial", "size": 12})
        theme.set_styles("bokeh", styles1)
        styles2 = ThemeStyles(font={"size": 14, "color": "red"})
        theme.update_styles("bokeh", styles2)
        assert theme.get_styles("bokeh").font == {
            "family": "Arial",
            "size": 14,
            "color": "red",
        }


class TestThemeRegistry:
    def test_register_and_get(self):
        registry = ThemeRegistry()
        theme = Theme("test_registry")
        registry.register(theme)
        assert registry.get("test_registry") == theme

    def test_register_duplicate(self):
        registry = ThemeRegistry()
        theme = Theme("test_dup")
        registry.register(theme)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(theme)

    def test_unregister(self):
        registry = ThemeRegistry()
        theme = Theme("test_unreg")
        registry.register(theme)
        assert registry.unregister("test_unreg") == theme
        assert "test_unreg" not in registry

    def test_list(self):
        registry = ThemeRegistry()
        registry.register(Theme("theme1"))
        registry.register(Theme("theme2"))
        assert registry.list() == ["theme1", "theme2"]

    def test_contains(self):
        registry = ThemeRegistry()
        registry.register(Theme("test_contain"))
        assert "test_contain" in registry
        assert "nonexistent" not in registry


class TestThemeState:
    def test_default_state(self):
        state = ThemeState()
        assert state.current is None

    def test_set_global(self):
        state = ThemeState()
        theme = Theme("test_global")
        state.set_global(theme)
        assert state.current == theme

    def test_push_pop(self):
        state = ThemeState()
        theme1 = Theme("theme1")
        theme2 = Theme("theme2")
        state.set_global(theme1)
        assert state.current == theme1
        state.push(theme2)
        assert state.current == theme2
        state.push(None)
        assert state.current is None
        assert state.pop() is None
        assert state.current == theme2
        assert state.pop() == theme2
        assert state.current == theme1

    def test_context_manager(self):
        hv.opts.defaults_theme(None)
        assert hv.opts.current_theme() is None
        with hv.opts.theme("presentation"):
            assert hv.opts.current_theme().name == "presentation"
            with hv.opts.theme("dark"):
                assert hv.opts.current_theme().name == "dark"
            assert hv.opts.current_theme().name == "presentation"
        assert hv.opts.current_theme() is None


class TestBuiltinThemes:
    def test_builtin_themes_registered(self):
        themes = list_themes()
        assert "default" in themes
        assert "presentation" in themes
        assert "dark" in themes
        assert "minimal" in themes
        assert "ggplot" in themes

    def test_presentation_theme(self):
        theme = get_theme("presentation")
        bokeh_styles = theme.get_styles("bokeh")
        assert bokeh_styles.font["size"] == "16pt"
        assert bokeh_styles.font["style"] == "bold"
        assert bokeh_styles.toolbar["autohide"] is True

    def test_dark_theme(self):
        theme = get_theme("dark")
        bokeh_styles = theme.get_styles("bokeh")
        assert bokeh_styles.background["color"] == "#222222"
        assert bokeh_styles.font["color"] == "#ffffff"

    def test_minimal_theme(self):
        theme = get_theme("minimal")
        bokeh_styles = theme.get_styles("bokeh")
        assert bokeh_styles.grid["show"] is False
        assert bokeh_styles.toolbar["position"] is None

    def test_ggplot_theme(self):
        theme = get_theme("ggplot")
        bokeh_styles = theme.get_styles("bokeh")
        assert bokeh_styles.background["color"] == "#ebebeb"
        assert bokeh_styles.grid["color"] == "#ffffff"


class TestThemeIntegration:
    @pytest.fixture(autouse=True)
    def cleanup(self):
        hv.opts.defaults_theme(None)
        yield
        hv.opts.defaults_theme(None)

    def test_defaults_theme(self):
        assert hv.opts.current_theme() is None
        hv.opts.defaults_theme("presentation")
        assert hv.opts.current_theme().name == "presentation"
        hv.opts.defaults_theme(None)
        assert hv.opts.current_theme() is None

    def test_list_themes(self):
        themes = hv.opts.list_themes()
        assert isinstance(themes, list)
        assert len(themes) >= 5

    def test_get_theme(self):
        theme = hv.opts.get_theme("default")
        assert theme.name == "default"
        with pytest.raises(ValueError, match="not found"):
            hv.opts.get_theme("nonexistent_theme")

    def test_register_and_unregister_theme(self):
        styles = ThemeStyles(font={"family": "Comic Sans"})
        theme = Theme("custom_test_theme", {"bokeh": styles})
        hv.opts.register_theme(theme)
        assert "custom_test_theme" in hv.opts.list_themes()
        assert hv.opts.get_theme("custom_test_theme") == theme
        hv.opts.unregister_theme("custom_test_theme")
        assert "custom_test_theme" not in hv.opts.list_themes()

    def test_register_duplicate_raises(self):
        theme = Theme("duplicate_test")
        hv.opts.register_theme(theme)
        with pytest.raises(ValueError, match="already registered"):
            hv.opts.register_theme(theme)
        hv.opts.unregister_theme("duplicate_test")

    def test_theme_with_bokeh_backend(self):
        pytest.importorskip("bokeh")
        hv.extension("bokeh")

        curve = hv.Curve([1, 2, 3, 4, 5])

        hv.opts.defaults_theme("presentation")
        opts = hv.Store.lookup_options("bokeh", curve, "plot")
        assert "text_font_size" in opts.kwargs

        hv.opts.defaults_theme(None)
        opts2 = hv.Store.lookup_options("bokeh", curve, "plot")
        assert opts2.kwargs.get("text_font_size") != "16pt"

    def test_per_object_theme_override(self):
        pytest.importorskip("bokeh")
        hv.extension("bokeh")

        hv.opts.defaults_theme("default")
        curve1 = hv.Curve([1, 2, 3]).opts(theme="dark")
        curve2 = hv.Curve([1, 2, 3])

        opts1 = hv.Store.lookup_options("bokeh", curve1, "plot")
        opts2 = hv.Store.lookup_options("bokeh", curve2, "plot")

        assert opts1.kwargs.get("bgcolor") == "#222222"
        assert opts2.kwargs.get("bgcolor") != "#222222"

    def test_theme_priority(self):
        pytest.importorskip("bokeh")
        hv.extension("bokeh")

        hv.opts.defaults_theme("default")

        curve = hv.Curve([1, 2, 3]).opts(theme="dark", bgcolor="#ff0000")
        opts = hv.Store.lookup_options("bokeh", curve, "plot")

        assert opts.kwargs["bgcolor"] == "#ff0000"

    def test_nested_theme_context(self):
        hv.opts.defaults_theme("default")

        with hv.opts.theme("presentation"):
            assert hv.opts.current_theme().name == "presentation"
            with hv.opts.theme("dark"):
                assert hv.opts.current_theme().name == "dark"
            assert hv.opts.current_theme().name == "presentation"
        assert hv.opts.current_theme().name == "default"

    def test_matplotlib_theme_styles(self):
        pytest.importorskip("matplotlib")
        theme = get_theme("presentation")
        mpl_styles = theme.get_styles("matplotlib")
        assert mpl_styles.font["size"] == 16

    def test_plotly_theme_styles(self):
        pytest.importorskip("plotly")
        theme = get_theme("dark")
        plotly_styles = theme.get_styles("plotly")
        assert plotly_styles.background["color"] == "#222222"

    def test_theme_parameter_not_leaked_to_backend(self):
        pytest.importorskip("bokeh")
        hv.extension("bokeh")

        curve = hv.Curve([1, 2, 3]).opts(theme="dark", bgcolor="#ff0000")
        opts = hv.Store.lookup_options("bokeh", curve, "plot")

        assert "theme" not in opts.kwargs

    def test_explicit_opts_override_theme(self):
        pytest.importorskip("bokeh")
        hv.extension("bokeh")

        hv.opts.defaults_theme("presentation")

        curve = hv.Curve([1, 2, 3]).opts(bgcolor="#ff0000")
        opts = hv.Store.lookup_options("bokeh", curve, "plot")

        assert opts.kwargs["bgcolor"] == "#ff0000"
        assert opts.kwargs.get("text_font_size") == "16pt"

    def test_object_theme_overrides_global(self):
        pytest.importorskip("bokeh")
        hv.extension("bokeh")

        hv.opts.defaults_theme("default")

        curve1 = hv.Curve([1, 2, 3]).opts(theme="dark")
        curve2 = hv.Curve([1, 2, 3])

        opts1 = hv.Store.lookup_options("bokeh", curve1, "plot")
        opts2 = hv.Store.lookup_options("bokeh", curve2, "plot")

        assert opts1.kwargs.get("bgcolor") == "#222222"
        assert opts2.kwargs.get("bgcolor") == "#ffffff"

    def test_context_theme_overrides_global(self):
        pytest.importorskip("bokeh")
        hv.extension("bokeh")

        hv.opts.defaults_theme("default")

        curve = hv.Curve([1, 2, 3])

        with hv.opts.theme("dark"):
            opts = hv.Store.lookup_options("bokeh", curve, "plot")
            assert opts.kwargs.get("bgcolor") == "#222222"

        opts2 = hv.Store.lookup_options("bokeh", curve, "plot")
        assert opts2.kwargs.get("bgcolor") == "#ffffff"

    def test_bokeh_legend_styles(self):
        pytest.importorskip("bokeh")
        theme = get_theme("presentation")
        from holoviews.core.theme import _theme_to_options

        opts = _theme_to_options(theme, "bokeh", "plot")
        assert "legend_position" in opts
        assert "legend_opts" in opts
        assert "label_text_font_size" in opts["legend_opts"]

    def test_bokeh_colorbar_styles(self):
        pytest.importorskip("bokeh")
        theme = get_theme("presentation")
        from holoviews.core.theme import _theme_to_options

        opts = _theme_to_options(theme, "bokeh", "plot")
        assert "colorbar_opts" in opts
        assert "title_text_font_size" in opts["colorbar_opts"]

    def test_bokeh_hover_styles(self):
        pytest.importorskip("bokeh")
        theme = get_theme("presentation")
        from holoviews.core.theme import _theme_to_options

        opts = _theme_to_options(theme, "bokeh", "style")
        assert "hover_fill_color" in opts
        assert "hover_fill_alpha" in opts

    def test_bokeh_toolbar_styles(self):
        pytest.importorskip("bokeh")
        theme = get_theme("presentation")
        from holoviews.core.theme import _theme_to_options

        opts = _theme_to_options(theme, "bokeh", "plot")
        assert opts["toolbar"] == "above"
        assert opts["autohide_toolbar"] is True

    def test_matplotlib_rcparams_integration(self):
        pytest.importorskip("matplotlib")
        theme = get_theme("presentation")
        from holoviews.core.theme import _theme_to_options

        opts = _theme_to_options(theme, "matplotlib", "plot")
        assert "fig_rcparams" in opts
        assert opts["fig_rcparams"]["font.size"] == 16

    def test_matplotlib_gridstyle_integration(self):
        pytest.importorskip("matplotlib")
        theme = get_theme("presentation")
        from holoviews.core.theme import _theme_to_options

        opts = _theme_to_options(theme, "matplotlib", "plot")
        assert "gridstyle" in opts
        assert "grid_color" in opts["gridstyle"]

    def test_plotly_layout_styles(self):
        pytest.importorskip("plotly")
        theme = get_theme("presentation")
        from holoviews.core.theme import _theme_to_options

        opts = _theme_to_options(theme, "plotly", "plot")
        assert "font_size" in opts
        assert "paper_bgcolor" in opts

    def test_plotly_hover_styles(self):
        pytest.importorskip("plotly")
        theme = get_theme("presentation")
        from holoviews.core.theme import _theme_to_options

        opts = _theme_to_options(theme, "plotly", "style")
        assert "hoverlabel_bgcolor" in opts
        assert "hoverlabel_font_size" in opts

    def test_full_priority_chain(self):
        pytest.importorskip("bokeh")
        hv.extension("bokeh")

        hv.opts.defaults_theme("default")

        curve = hv.Curve([1, 2, 3]).opts(theme="dark", bgcolor="#ff0000")

        with hv.opts.theme("presentation"):
            opts = hv.Store.lookup_options("bokeh", curve, "plot")
            assert opts.kwargs["bgcolor"] == "#ff0000"
            assert opts.kwargs.get("text_font_size") == "12pt"

    def test_theme_in_style_options_not_leaked(self):
        pytest.importorskip("bokeh")
        hv.extension("bokeh")

        curve = hv.Curve([1, 2, 3]).opts(theme="dark")
        opts = hv.Store.lookup_options("bokeh", curve, "style")

        assert "theme" not in opts.kwargs


class TestThemeApi:
    def test_module_level_functions(self):
        assert callable(register_theme)
        assert callable(unregister_theme)
        assert callable(get_theme)
        assert callable(list_themes)
        assert callable(set_default_theme)
        assert callable(get_default_theme)
        assert callable(theme_context)
        assert callable(get_active_theme)

    def test_module_level_registry(self):
        assert isinstance(theme_registry, ThemeRegistry)
        assert isinstance(theme_state, ThemeState)


# ---------------------------------------------------------------------------
# Actual-rendering assertions per backend
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _register_test_theme():
    if "__test_theme__" in hv.opts.list_themes():
        return
    hv.opts.register_theme(
        Theme(
            "__test_theme__",
            bokeh=ThemeStyles(
                font={"family": "Courier New", "size": 18, "color": "#112233"},
                background={"color": "#F5F5F5"},
                grid={"show": True, "color": "#AAAAAA", "alpha": 0.6, "line_width": 1.5},
                legend={"font_size": 13, "bgcolor": "#FFFFFF", "borderwidth": 0},
                toolbar={"autohide": True},
                colorbar={"title_font_size": 14, "tick_font_size": 10, "bgcolor": "#FFFFFF"},
                hover={"mode": "vline", "background_color": "#FFFFE0"},
            ),
            matplotlib=ThemeStyles(
                font={"family": "DejaVu Sans", "size": 16},
                background={"color": "#FFF8DC"},
                grid={"show": True, "color": "#A9A9A9"},
                legend={"fontsize": 12, "framealpha": 0.8, "facecolor": "#FFFAF0"},
                toolbar={"show": True},
                colorbar={"labelsize": 11},
            ),
            plotly=ThemeStyles(
                font={"family": "Verdana", "size": 16, "color": "#222222"},
                background={"color": "#FAF0E6"},
                grid={"show": True, "color": "#D3D3D3", "width": 1},
                legend={"font_size": 13, "bgcolor": "#FFFAF0", "position": "top_right"},
                colorbar={"title_font_size": 13, "tick_font_size": 10},
                hover={"mode": "closest", "background_color": "#FFFFFF"},
            ),
        )
    )


class TestThemeCapabilitiesDowngrade:
    def test_unsupported_keys_logged_as_info(self, caplog):
        import logging

        from holoviews.core.theme import ThemeCapabilities

        caplog.set_level(logging.INFO)
        raw = ThemeStyles(toolbar={"show": True, "unknown": 1})
        # Plotly declares no toolbar support
        ThemeCapabilities.filter_styles(raw, "plotly", warn=True)
        assert any("toolbar" in rec.message for rec in caplog.records)


class TestUserExplicitKeys:
    def test_user_opts_detected_via_store_lookup(self, _register_test_theme):
        import holoviews as hv
        from holoviews.core.theme import get_user_explicit_keys

        hv.extension("bokeh")
        curve = hv.Curve([1, 2, 3]).opts(
            bgcolor="#FF0000", legend_position="top_left"
        )
        renderer = hv.renderer("bokeh")
        plot = renderer.get_plot(curve)
        user_keys = get_user_explicit_keys(plot, "bokeh")
        assert "color" in user_keys["background"]
        assert "position" in user_keys["legend"]


class TestBokehActualRendering:
    def test_theme_applied_to_figure(self, _register_test_theme):
        import holoviews as hv

        hv.extension("bokeh")
        with hv.opts.theme("__test_theme__"):
            curve = hv.Curve([1, 2, 3])
            renderer = hv.renderer("bokeh")
            plot = renderer.get_plot(curve)
            state = plot.state
            assert state.background_fill_color == "#F5F5F5"
            assert state.title.text_font == "Courier New"
            assert state.toolbar.autohide is True
            # grid
            for g in state.xgrid:
                assert g.grid_line_color == "#AAAAAA"
                assert g.grid_line_alpha == 0.6
                assert g.grid_line_width == 1.5
            # axes font
            for ax in state.xaxis:
                assert ax.axis_label_text_font == "Courier New"
                assert ax.major_label_text_font == "Courier New"

    def test_user_opts_not_overwritten(self, _register_test_theme):
        import holoviews as hv

        hv.extension("bokeh")
        with hv.opts.theme("__test_theme__"):
            curve = hv.Curve([1, 2, 3]).opts(bgcolor="#0000FF")
            renderer = hv.renderer("bokeh")
            plot = renderer.get_plot(curve)
            assert plot.state.background_fill_color == "#0000FF"

    def test_theme_applied_to_legend(self, _register_test_theme):
        import holoviews as hv

        hv.extension("bokeh")
        with hv.opts.theme("__test_theme__"):
            overlay = hv.Curve([1, 2, 3], label="A") * hv.Curve([3, 2, 1], label="B")
            renderer = hv.renderer("bokeh")
            plot = renderer.get_plot(overlay)
            assert plot.state.legend
            for leg in plot.state.legend:
                font_size_val = leg.label_text_font_size
                if isinstance(font_size_val, str):
                    assert font_size_val.startswith("13")
                else:
                    assert str(font_size_val).startswith("13")
                assert leg.background_fill_color == "#FFFFFF"

    def test_theme_applied_to_hover(self, _register_test_theme):
        import holoviews as hv
        from bokeh.models import HoverTool

        hv.extension("bokeh")
        with hv.opts.theme("__test_theme__"):
            curve = hv.Curve([1, 2, 3])
            renderer = hv.renderer("bokeh")
            plot = renderer.get_plot(curve)
            hovers = [t for t in plot.state.tools if isinstance(t, HoverTool)]
            assert hovers
            h = hovers[0]
            assert h.background == "#FFFFE0"


class TestMatplotlibActualRendering:
    def test_theme_applied_to_figure(self, _register_test_theme):
        import holoviews as hv
        from matplotlib.colors import to_rgb

        hv.extension("matplotlib")
        with hv.opts.theme("__test_theme__"):
            curve = hv.Curve([1, 2, 3])
            renderer = hv.renderer("matplotlib")
            plot = renderer.get_plot(curve)
            fig = plot.state.figure
            expected_bg = to_rgb("#FFF8DC")
            assert to_rgb(fig.get_facecolor()[:3]) == expected_bg
            ax = fig.axes[0]
            assert to_rgb(ax.get_facecolor()[:3]) == expected_bg
            expected_grid = to_rgb("#A9A9A9")
            assert to_rgb(ax.yaxis.get_gridlines()[0].get_color()[:3]) == expected_grid

    def test_user_opts_not_overwritten_mpl(self, _register_test_theme):
        import holoviews as hv
        from matplotlib.colors import to_rgb

        hv.extension("matplotlib")
        with hv.opts.theme("__test_theme__"):
            curve = hv.Curve([1, 2, 3]).opts(bgcolor="#00FF00")
            renderer = hv.renderer("matplotlib")
            plot = renderer.get_plot(curve)
            ax = plot.state.figure.axes[0]
            assert to_rgb(ax.get_facecolor()[:3]) == to_rgb("#00FF00")


class TestPlotlyActualRendering:
    def test_theme_applied_to_layout(self, _register_test_theme):
        import holoviews as hv

        hv.extension("plotly")
        with hv.opts.theme("__test_theme__"):
            curve = hv.Curve([1, 2, 3])
            renderer = hv.renderer("plotly")
            fig = renderer.get_plot(curve).state
            assert fig.layout["font"]["family"] == "Verdana"
            assert fig.layout["font"]["size"] == 16
            assert fig.layout["paper_bgcolor"] == "#FAF0E6"
            assert fig.layout["plot_bgcolor"] == "#FAF0E6"
            assert fig.layout["hovermode"] == "closest"
            assert fig.layout["hoverlabel"]["bgcolor"] == "#FFFFFF"
            assert fig.layout["xaxis"]["showgrid"] is True
            assert fig.layout["xaxis"]["gridcolor"] == "#D3D3D3"
            assert fig.layout["legend"]["x"] == 1.02
            assert fig.layout["legend"]["y"] == 1

    def test_user_opts_not_overwritten_plotly(self, _register_test_theme):
        import holoviews as hv

        hv.extension("plotly")
        with hv.opts.theme("__test_theme__"):
            curve = hv.Curve([1, 2, 3]).opts(bgcolor="#0000FF")
            renderer = hv.renderer("plotly")
            fig = renderer.get_plot(curve).state
            assert fig.layout["paper_bgcolor"] == "#0000FF"
            assert fig.layout["plot_bgcolor"] == "#0000FF"
