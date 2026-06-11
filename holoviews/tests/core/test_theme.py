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
