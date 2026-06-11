from __future__ import annotations

import typing as t
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import local

if t.TYPE_CHECKING:
    from .options import Options


_BACKEND_T = t.Literal["bokeh", "matplotlib", "plotly"]
_BACKENDS: tuple[_BACKEND_T, ...] = ("bokeh", "matplotlib", "plotly")


@dataclass
class ThemeStyles:
    font: dict[str, t.Any] = field(default_factory=dict)
    grid: dict[str, t.Any] = field(default_factory=dict)
    background: dict[str, t.Any] = field(default_factory=dict)
    legend: dict[str, t.Any] = field(default_factory=dict)
    toolbar: dict[str, t.Any] = field(default_factory=dict)
    colorbar: dict[str, t.Any] = field(default_factory=dict)
    hover: dict[str, t.Any] = field(default_factory=dict)

    def merge(self, other: "ThemeStyles") -> "ThemeStyles":
        merged = ThemeStyles()
        for attr in self.__dataclass_fields__:
            merged_val = dict(getattr(self, attr))
            merged_val.update(getattr(other, attr))
            setattr(merged, attr, merged_val)
        return merged

    def to_dict(self) -> dict[str, t.Any]:
        return {
            attr: getattr(self, attr).copy()
            for attr in self.__dataclass_fields__
        }


class Theme:
    def __init__(
        self,
        name: str,
        styles: dict[_BACKEND_T, ThemeStyles] | None = None,
        description: str = "",
    ) -> None:
        self.name = name
        self.description = description
        self._styles: dict[_BACKEND_T, ThemeStyles] = styles or {}
        for backend in _BACKENDS:
            if backend not in self._styles:
                self._styles[backend] = ThemeStyles()

    def get_styles(self, backend: _BACKEND_T) -> ThemeStyles:
        if backend not in self._styles:
            raise ValueError(
                f"Backend {backend!r} not supported by theme {self.name!r}. "
                f"Supported backends: {list(self._styles.keys())}"
            )
        return self._styles[backend]

    def set_styles(self, backend: _BACKEND_T, styles: ThemeStyles) -> None:
        self._styles[backend] = styles

    def update_styles(self, backend: _BACKEND_T, styles: ThemeStyles) -> None:
        if backend in self._styles:
            self._styles[backend] = self._styles[backend].merge(styles)
        else:
            self._styles[backend] = styles


class ThemeRegistry:
    def __init__(self) -> None:
        self._themes: dict[str, Theme] = {}

    def register(self, theme: Theme) -> None:
        if theme.name in self._themes:
            raise ValueError(f"Theme {theme.name!r} is already registered")
        self._themes[theme.name] = theme

    def unregister(self, name: str) -> Theme | None:
        return self._themes.pop(name, None)

    def get(self, name: str) -> Theme:
        if name not in self._themes:
            available = ", ".join(repr(t) for t in self._themes.keys())
            raise ValueError(
                f"Theme {name!r} not found. Available themes: {available}"
            )
        return self._themes[name]

    def list(self) -> list[str]:
        return sorted(self._themes.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._themes

    def __iter__(self) -> t.Iterator[Theme]:
        return iter(self._themes.values())


class ThemeState(local):
    def __init__(self) -> None:
        self._stack: list[Theme | None] = [None]

    @property
    def current(self) -> Theme | None:
        return self._stack[-1] if self._stack else None

    def push(self, theme: Theme | None) -> None:
        self._stack.append(theme)

    def pop(self) -> Theme | None:
        if len(self._stack) > 1:
            return self._stack.pop()
        return None

    def set_global(self, theme: Theme | None) -> None:
        self._stack[0] = theme


theme_registry = ThemeRegistry()
theme_state = ThemeState()


def register_theme(theme: Theme) -> None:
    theme_registry.register(theme)


def unregister_theme(name: str) -> Theme | None:
    return theme_registry.unregister(name)


def get_theme(name: str) -> Theme:
    return theme_registry.get(name)


def list_themes() -> list[str]:
    return theme_registry.list()


def set_default_theme(theme: str | Theme | None) -> None:
    if isinstance(theme, str):
        theme = get_theme(theme)
    theme_state.set_global(theme)


def get_default_theme() -> Theme | None:
    return theme_state.current


@contextmanager
def theme_context(theme: str | Theme | None) -> t.Generator[None, None, None]:
    if isinstance(theme, str):
        theme = get_theme(theme)
    theme_state.push(theme)
    try:
        yield
    finally:
        theme_state.pop()


def get_active_theme() -> Theme | None:
    return theme_state.current


def _merge_options_with_theme(
    options: "Options",
    theme: Theme | None,
    backend: _BACKEND_T,
    group: str,
) -> "Options":
    if theme is None:
        return options

    from .options import Options

    theme_opts = _theme_to_options(theme, backend, group)
    if not theme_opts:
        return options

    merged_kwargs = dict(theme_opts)
    merged_kwargs.update(options.kwargs)

    return Options(
        key=options.key,
        allowed_keywords=options.allowed_keywords,
        merge_keywords=options.merge_keywords,
        **merged_kwargs,
    )


def _theme_to_options(
    theme: Theme,
    backend: _BACKEND_T,
    group: str,
) -> dict[str, t.Any]:
    styles = theme.get_styles(backend)
    result: dict[str, t.Any] = {}

    if group == "plot":
        result.update(_styles_to_plot_options(styles, backend))
    elif group == "style":
        result.update(_styles_to_style_options(styles, backend))

    return result


def _styles_to_plot_options(styles: ThemeStyles, backend: _BACKEND_T) -> dict[str, t.Any]:
    opts: dict[str, t.Any] = {}

    if backend == "bokeh":
        if styles.font:
            if "family" in styles.font:
                opts["text_font"] = styles.font["family"]
            if "size" in styles.font:
                opts["text_font_size"] = styles.font["size"]
            if "style" in styles.font:
                opts["text_font_style"] = styles.font["style"]
            if "color" in styles.font:
                opts["text_color"] = styles.font["color"]

        if styles.background:
            if "color" in styles.background:
                opts["bgcolor"] = styles.background["color"]

        if styles.toolbar:
            if "position" in styles.toolbar:
                opts["toolbar"] = styles.toolbar["position"]
            if "autohide" in styles.toolbar:
                opts["autohide_toolbar"] = styles.toolbar["autohide"]

        if styles.legend:
            if "position" in styles.legend:
                opts["legend_position"] = styles.legend["position"]
            if "click_policy" in styles.legend:
                opts["legend_click_policy"] = styles.legend["click_policy"]

        if styles.grid:
            if "show" in styles.grid:
                opts["show_grid"] = styles.grid["show"]
            if "xaxis" in styles.grid:
                opts["xaxis"] = styles.grid["xaxis"]
            if "yaxis" in styles.grid:
                opts["yaxis"] = styles.grid["yaxis"]

        if styles.hover:
            if "tooltips" in styles.hover:
                opts["tooltips"] = styles.hover["tooltips"]

    elif backend == "matplotlib":
        if styles.font:
            if "family" in styles.font:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["font.family"] = styles.font["family"]
            if "size" in styles.font:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["font.size"] = styles.font["size"]

        if styles.background:
            if "color" in styles.background:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["figure.facecolor"] = styles.background["color"]
                opts["fig_rcparams"]["axes.facecolor"] = styles.background["color"]

        if styles.grid:
            gridstyle = {}
            if "color" in styles.grid:
                gridstyle["grid_color"] = styles.grid["color"]
            if "alpha" in styles.grid:
                gridstyle["grid_alpha"] = styles.grid["alpha"]
            if "line_width" in styles.grid:
                gridstyle["grid_linewidth"] = styles.grid["line_width"]
            if "linestyle" in styles.grid:
                gridstyle["grid_linestyle"] = styles.grid["linestyle"]
            if gridstyle:
                opts["gridstyle"] = gridstyle

        if styles.legend:
            if "position" in styles.legend:
                opts["legend_position"] = styles.legend["position"]
            if "frame" in styles.legend:
                opts["show_legend_frame"] = styles.legend["frame"]

        if styles.toolbar:
            if "show" in styles.toolbar:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["toolbar"] = (
                    "toolbar2" if styles.toolbar["show"] else "None"
                )

    elif backend == "plotly":
        if styles.font:
            if "family" in styles.font:
                opts["font_family"] = styles.font["family"]
            if "size" in styles.font:
                opts["font_size"] = styles.font["size"]
            if "color" in styles.font:
                opts["font_color"] = styles.font["color"]

        if styles.background:
            if "color" in styles.background:
                opts["paper_bgcolor"] = styles.background["color"]
                opts["plot_bgcolor"] = styles.background["color"]

        if styles.grid:
            if "show" in styles.grid:
                opts["showgrid"] = styles.grid["show"]
            if "color" in styles.grid:
                opts["gridcolor"] = styles.grid["color"]

        if styles.legend:
            if "position" in styles.legend:
                pos = styles.legend["position"]
                if isinstance(pos, tuple):
                    opts["legend_x"] = pos[0]
                    opts["legend_y"] = pos[1]
            if "orientation" in styles.legend:
                opts["legend_orientation"] = styles.legend["orientation"]

        if styles.toolbar:
            if "show" in styles.toolbar:
                opts["showlegend"] = styles.toolbar["show"]

    return opts


def _styles_to_style_options(styles: ThemeStyles, backend: _BACKEND_T) -> dict[str, t.Any]:
    opts: dict[str, t.Any] = {}

    if backend == "bokeh":
        if styles.font:
            if "family" in styles.font:
                opts["text_font"] = styles.font["family"]
            if "size" in styles.font:
                opts["text_font_size"] = styles.font["size"]
            if "style" in styles.font:
                opts["text_font_style"] = styles.font["style"]
            if "color" in styles.font:
                opts["text_color"] = styles.font["color"]

        if styles.grid:
            if "color" in styles.grid:
                opts["grid_line_color"] = styles.grid["color"]
            if "alpha" in styles.grid:
                opts["grid_line_alpha"] = styles.grid["alpha"]
            if "line_width" in styles.grid:
                opts["grid_line_width"] = styles.grid["line_width"]
            if "linestyle" in styles.grid:
                opts["grid_line_dash"] = styles.grid["linestyle"]

        if styles.hover:
            if "background_color" in styles.hover:
                opts["hover_fill_color"] = styles.hover["background_color"]
            if "alpha" in styles.hover:
                opts["hover_fill_alpha"] = styles.hover["alpha"]
            if "line_color" in styles.hover:
                opts["hover_line_color"] = styles.hover["line_color"]

        if styles.colorbar:
            if "title_text_font_size" in styles.colorbar:
                opts["colorbar_title_text_font_size"] = styles.colorbar["title_text_font_size"]
            if "major_label_text_font_size" in styles.colorbar:
                opts["colorbar_major_label_text_font_size"] = styles.colorbar["major_label_text_font_size"]

    elif backend == "matplotlib":
        if styles.colorbar:
            if "labelsize" in styles.colorbar:
                opts["cbar_kws"] = opts.get("cbar_kws", {})
                opts["cbar_kws"]["labelsize"] = styles.colorbar["labelsize"]

    elif backend == "plotly":
        if styles.hover:
            if "background_color" in styles.hover:
                opts["hoverlabel_bgcolor"] = styles.hover["background_color"]
            if "font_size" in styles.hover:
                opts["hoverlabel_font_size"] = styles.hover["font_size"]

        if styles.colorbar:
            if "title_font_size" in styles.colorbar:
                opts["colorbar_title_font_size"] = styles.colorbar["title_font_size"]
            if "tick_font_size" in styles.colorbar:
                opts["colorbar_tick_font_size"] = styles.colorbar["tick_font_size"]

    return opts


def _register_builtin_themes() -> None:
    default_theme = Theme(
        name="default",
        description="The default HoloViews theme with sensible defaults.",
        styles={
            "bokeh": ThemeStyles(
                font={"family": "Helvetica", "size": "12pt"},
                grid={"show": True, "color": "#e0e0e0"},
                background={"color": "#ffffff"},
                legend={"position": "top_right"},
                toolbar={"position": "above", "autohide": False},
            ),
            "matplotlib": ThemeStyles(
                font={"family": "sans-serif", "size": 12},
                grid={"show": True, "color": "#e0e0e0", "line_width": 0.5},
                background={"color": "#ffffff"},
                legend={"position": "best", "frame": True},
                toolbar={"show": True},
            ),
            "plotly": ThemeStyles(
                font={"family": "Arial", "size": 12},
                grid={"show": True, "color": "#e0e0e0"},
                background={"color": "#ffffff"},
                legend={"position": (1.02, 1)},
                toolbar={"show": True},
            ),
        },
    )

    presentation_theme = Theme(
        name="presentation",
        description="A theme optimized for presentations with larger fonts and bold styling.",
        styles={
            "bokeh": ThemeStyles(
                font={"family": "Helvetica", "size": "16pt", "style": "bold"},
                grid={"show": True, "color": "#c0c0c0", "line_width": 1.5},
                background={"color": "#ffffff"},
                legend={"position": "top_right", "click_policy": "hide"},
                toolbar={"position": "above", "autohide": True},
                colorbar={"title_text_font_size": "14pt", "major_label_text_font_size": "12pt"},
                hover={"background_color": "#f0f0f0", "alpha": 0.95},
            ),
            "matplotlib": ThemeStyles(
                font={"family": "sans-serif", "size": 16},
                grid={"show": True, "color": "#c0c0c0", "line_width": 1.5},
                background={"color": "#ffffff"},
                legend={"position": "best", "frame": True},
                toolbar={"show": True},
                colorbar={"labelsize": 12},
            ),
            "plotly": ThemeStyles(
                font={"family": "Arial", "size": 16},
                grid={"show": True, "color": "#c0c0c0"},
                background={"color": "#ffffff"},
                legend={"position": (1.02, 1)},
                toolbar={"show": True},
                colorbar={"title_font_size": 14, "tick_font_size": 12},
                hover={"font_size": 14},
            ),
        },
    )

    dark_theme = Theme(
        name="dark",
        description="A dark theme with high contrast colors.",
        styles={
            "bokeh": ThemeStyles(
                font={"family": "Helvetica", "size": "12pt", "color": "#ffffff"},
                grid={"show": True, "color": "#404040"},
                background={"color": "#222222"},
                legend={"position": "top_right"},
                toolbar={"position": "above", "autohide": False},
                hover={"background_color": "#333333", "line_color": "#666666"},
            ),
            "matplotlib": ThemeStyles(
                font={"family": "sans-serif", "size": 12},
                grid={"show": True, "color": "#404040", "line_width": 0.5},
                background={"color": "#222222"},
                legend={"position": "best", "frame": True},
                toolbar={"show": True},
            ),
            "plotly": ThemeStyles(
                font={"family": "Arial", "size": 12, "color": "#ffffff"},
                grid={"show": True, "color": "#404040"},
                background={"color": "#222222"},
                legend={"position": (1.02, 1)},
                toolbar={"show": True},
                hover={"background_color": "#333333"},
            ),
        },
    )

    minimal_theme = Theme(
        name="minimal",
        description="A clean, minimal theme with minimal decorations.",
        styles={
            "bokeh": ThemeStyles(
                font={"family": "Helvetica", "size": "11pt"},
                grid={"show": False},
                background={"color": "#ffffff"},
                legend={"position": "top_right"},
                toolbar={"position": None},
                hover={"background_color": "#fafafa"},
            ),
            "matplotlib": ThemeStyles(
                font={"family": "sans-serif", "size": 11},
                grid={"show": False},
                background={"color": "#ffffff"},
                legend={"position": "best", "frame": False},
                toolbar={"show": False},
            ),
            "plotly": ThemeStyles(
                font={"family": "Arial", "size": 11},
                grid={"show": False},
                background={"color": "#ffffff"},
                legend={"position": (1.02, 1)},
                toolbar={"show": False},
            ),
        },
    )

    ggplot_theme = Theme(
        name="ggplot",
        description="A theme inspired by R's ggplot2.",
        styles={
            "bokeh": ThemeStyles(
                font={"family": "Helvetica", "size": "12pt"},
                grid={"show": True, "color": "#ffffff", "line_width": 1},
                background={"color": "#ebebeb"},
                legend={"position": "top_right"},
                toolbar={"position": "above"},
            ),
            "matplotlib": ThemeStyles(
                font={"family": "sans-serif", "size": 12},
                grid={"show": True, "color": "#ffffff", "line_width": 1},
                background={"color": "#ebebeb"},
                legend={"position": "best", "frame": True},
                toolbar={"show": True},
            ),
            "plotly": ThemeStyles(
                font={"family": "Arial", "size": 12},
                grid={"show": True, "color": "#ffffff"},
                background={"color": "#ebebeb"},
                legend={"position": (1.02, 1)},
                toolbar={"show": True},
            ),
        },
    )

    for theme in [default_theme, presentation_theme, dark_theme, minimal_theme, ggplot_theme]:
        theme_registry.register(theme)


_register_builtin_themes()
