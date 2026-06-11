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
            if "border_color" in styles.background:
                opts["border_fill_color"] = styles.background["border_color"]

        if styles.toolbar:
            if "position" in styles.toolbar:
                opts["toolbar"] = styles.toolbar["position"]
            if "autohide" in styles.toolbar:
                opts["autohide_toolbar"] = styles.toolbar["autohide"]
            if "show" in styles.toolbar and not styles.toolbar["show"]:
                opts["toolbar"] = None

        if styles.legend:
            if "position" in styles.legend:
                opts["legend_position"] = styles.legend["position"]
            if "click_policy" in styles.legend:
                opts["legend_click_policy"] = styles.legend["click_policy"]
            if "show" in styles.legend:
                opts["show_legend"] = styles.legend["show"]
            if "cols" in styles.legend:
                opts["legend_cols"] = styles.legend["cols"]
            if "muted" in styles.legend:
                opts["legend_muted"] = styles.legend["muted"]
            legend_opts = {}
            if "label_text_font_size" in styles.legend:
                legend_opts["label_text_font_size"] = styles.legend["label_text_font_size"]
            if "label_text_font" in styles.legend:
                legend_opts["label_text_font"] = styles.legend["label_text_font"]
            if "label_text_color" in styles.legend:
                legend_opts["label_text_color"] = styles.legend["label_text_color"]
            if "title_text_font_size" in styles.legend:
                legend_opts["title_text_font_size"] = styles.legend["title_text_font_size"]
            if "title_text_font" in styles.legend:
                legend_opts["title_text_font"] = styles.legend["title_text_font"]
            if "title_text_color" in styles.legend:
                legend_opts["title_text_color"] = styles.legend["title_text_color"]
            if "background_fill_color" in styles.legend:
                legend_opts["background_fill_color"] = styles.legend["background_fill_color"]
            if "background_fill_alpha" in styles.legend:
                legend_opts["background_fill_alpha"] = styles.legend["background_fill_alpha"]
            if "border_line_color" in styles.legend:
                legend_opts["border_line_color"] = styles.legend["border_line_color"]
            if "border_line_alpha" in styles.legend:
                legend_opts["border_line_alpha"] = styles.legend["border_line_alpha"]
            if "border_line_width" in styles.legend:
                legend_opts["border_line_width"] = styles.legend["border_line_width"]
            if "spacing" in styles.legend:
                legend_opts["spacing"] = styles.legend["spacing"]
            if "padding" in styles.legend:
                legend_opts["padding"] = styles.legend["padding"]
            if legend_opts:
                opts["legend_opts"] = legend_opts

        if styles.grid:
            if "show" in styles.grid:
                opts["show_grid"] = styles.grid["show"]
            if "xaxis" in styles.grid:
                opts["xaxis"] = styles.grid["xaxis"]
            if "yaxis" in styles.grid:
                opts["yaxis"] = styles.grid["yaxis"]
            gridstyle = {}
            if "color" in styles.grid:
                gridstyle["grid_line_color"] = styles.grid["color"]
            if "alpha" in styles.grid:
                gridstyle["grid_line_alpha"] = styles.grid["alpha"]
            if "line_width" in styles.grid:
                gridstyle["grid_line_width"] = styles.grid["line_width"]
            if "linestyle" in styles.grid:
                gridstyle["grid_line_dash"] = styles.grid["linestyle"]
            if gridstyle:
                opts["gridstyle"] = gridstyle

        if styles.hover:
            if "tooltips" in styles.hover:
                opts["hover_tooltips"] = styles.hover["tooltips"]
            if "mode" in styles.hover:
                opts["hover_mode"] = styles.hover["mode"]
            if "show" in styles.hover:
                if styles.hover["show"]:
                    opts.setdefault("tools", []).append("hover")

        if styles.colorbar:
            if "show" in styles.colorbar:
                opts["colorbar"] = styles.colorbar["show"]
            if "position" in styles.colorbar:
                opts["colorbar_position"] = styles.colorbar["position"]
            colorbar_opts = {}
            if "title_text_font_size" in styles.colorbar:
                colorbar_opts["title_text_font_size"] = styles.colorbar["title_text_font_size"]
            if "title_text_font" in styles.colorbar:
                colorbar_opts["title_text_font"] = styles.colorbar["title_text_font"]
            if "title_text_color" in styles.colorbar:
                colorbar_opts["title_text_color"] = styles.colorbar["title_text_color"]
            if "major_label_text_font_size" in styles.colorbar:
                colorbar_opts["major_label_text_font_size"] = styles.colorbar["major_label_text_font_size"]
            if "major_label_text_font" in styles.colorbar:
                colorbar_opts["major_label_text_font"] = styles.colorbar["major_label_text_font"]
            if "major_label_text_color" in styles.colorbar:
                colorbar_opts["major_label_text_color"] = styles.colorbar["major_label_text_color"]
            if "background_fill_color" in styles.colorbar:
                colorbar_opts["background_fill_color"] = styles.colorbar["background_fill_color"]
            if "border_line_color" in styles.colorbar:
                colorbar_opts["border_line_color"] = styles.colorbar["border_line_color"]
            if "bar_line_color" in styles.colorbar:
                colorbar_opts["bar_line_color"] = styles.colorbar["bar_line_color"]
            if "scale_alpha" in styles.colorbar:
                colorbar_opts["scale_alpha"] = styles.colorbar["scale_alpha"]
            if colorbar_opts:
                opts["colorbar_opts"] = colorbar_opts

    elif backend == "matplotlib":
        if styles.font:
            if "family" in styles.font:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["font.family"] = styles.font["family"]
            if "size" in styles.font:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["font.size"] = styles.font["size"]
            if "weight" in styles.font:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["font.weight"] = styles.font["weight"]

        if styles.background:
            if "color" in styles.background:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["figure.facecolor"] = styles.background["color"]
                opts["fig_rcparams"]["axes.facecolor"] = styles.background["color"]
            if "edge_color" in styles.background:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["axes.edgecolor"] = styles.background["edge_color"]

        if styles.grid:
            gridstyle = {}
            if "show" in styles.grid:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["axes.grid"] = styles.grid["show"]
            if "color" in styles.grid:
                gridstyle["grid_color"] = styles.grid["color"]
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["grid.color"] = styles.grid["color"]
            if "alpha" in styles.grid:
                gridstyle["grid_alpha"] = styles.grid["alpha"]
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["grid.alpha"] = styles.grid["alpha"]
            if "line_width" in styles.grid:
                gridstyle["grid_linewidth"] = styles.grid["line_width"]
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["grid.linewidth"] = styles.grid["line_width"]
            if "linestyle" in styles.grid:
                gridstyle["grid_linestyle"] = styles.grid["linestyle"]
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["grid.linestyle"] = styles.grid["linestyle"]
            if gridstyle:
                opts["gridstyle"] = gridstyle

        if styles.legend:
            if "position" in styles.legend:
                opts["legend_position"] = styles.legend["position"]
            if "frame" in styles.legend:
                opts["show_legend_frame"] = styles.legend["frame"]
            if "show" in styles.legend:
                opts["show_legend"] = styles.legend["show"]
            if "fontsize" in styles.legend:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["legend.fontsize"] = styles.legend["fontsize"]
            if "title_fontsize" in styles.legend:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["legend.title_fontsize"] = styles.legend["title_fontsize"]
            if "framealpha" in styles.legend:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["legend.framealpha"] = styles.legend["framealpha"]
            if "edgecolor" in styles.legend:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["legend.edgecolor"] = styles.legend["edgecolor"]
            if "facecolor" in styles.legend:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["legend.facecolor"] = styles.legend["facecolor"]
            if "borderpad" in styles.legend:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["legend.borderpad"] = styles.legend["borderpad"]
            if "labelspacing" in styles.legend:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["legend.labelspacing"] = styles.legend["labelspacing"]

        if styles.toolbar:
            if "show" in styles.toolbar:
                opts["fig_rcparams"] = opts.get("fig_rcparams", {})
                opts["fig_rcparams"]["toolbar"] = (
                    "toolbar2" if styles.toolbar["show"] else "None"
                )

        if styles.colorbar:
            colorbar_opts = {}
            if "labelsize" in styles.colorbar:
                colorbar_opts["labelsize"] = styles.colorbar["labelsize"]
            if "pad" in styles.colorbar:
                colorbar_opts["pad"] = styles.colorbar["pad"]
            if "shrink" in styles.colorbar:
                colorbar_opts["shrink"] = styles.colorbar["shrink"]
            if "aspect" in styles.colorbar:
                colorbar_opts["aspect"] = styles.colorbar["aspect"]
            if "fraction" in styles.colorbar:
                colorbar_opts["fraction"] = styles.colorbar["fraction"]
            if colorbar_opts:
                opts["colorbar_opts"] = colorbar_opts

        if styles.hover:
            pass

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
            if "width" in styles.grid:
                opts["gridwidth"] = styles.grid["width"]

        if styles.legend:
            if "position" in styles.legend:
                pos = styles.legend["position"]
                if isinstance(pos, tuple):
                    opts["legend_x"] = pos[0]
                    opts["legend_y"] = pos[1]
            if "orientation" in styles.legend:
                opts["legend_orientation"] = styles.legend["orientation"]
            if "show" in styles.legend:
                opts["showlegend"] = styles.legend["show"]
            if "bgcolor" in styles.legend:
                opts["legend_bgcolor"] = styles.legend["bgcolor"]
            if "bordercolor" in styles.legend:
                opts["legend_bordercolor"] = styles.legend["bordercolor"]
            if "borderwidth" in styles.legend:
                opts["legend_borderwidth"] = styles.legend["borderwidth"]
            if "font_size" in styles.legend:
                opts["legend_font_size"] = styles.legend["font_size"]
            if "font_family" in styles.legend:
                opts["legend_font_family"] = styles.legend["font_family"]
            if "font_color" in styles.legend:
                opts["legend_font_color"] = styles.legend["font_color"]
            if "title_font_size" in styles.legend:
                opts["legend_title_font_size"] = styles.legend["title_font_size"]
            if "title_font_family" in styles.legend:
                opts["legend_title_font_family"] = styles.legend["title_font_family"]
            if "title_font_color" in styles.legend:
                opts["legend_title_font_color"] = styles.legend["title_font_color"]

        if styles.toolbar:
            pass

        if styles.colorbar:
            if "show" in styles.colorbar:
                opts["colorbar"] = styles.colorbar["show"]
            colorbar_opts = {}
            if "title_font_size" in styles.colorbar:
                colorbar_opts["title_font_size"] = styles.colorbar["title_font_size"]
            if "title_font_family" in styles.colorbar:
                colorbar_opts["title_font_family"] = styles.colorbar["title_font_family"]
            if "title_font_color" in styles.colorbar:
                colorbar_opts["title_font_color"] = styles.colorbar["title_font_color"]
            if "tick_font_size" in styles.colorbar:
                colorbar_opts["tick_font_size"] = styles.colorbar["tick_font_size"]
            if "tick_font_family" in styles.colorbar:
                colorbar_opts["tick_font_family"] = styles.colorbar["tick_font_family"]
            if "tick_font_color" in styles.colorbar:
                colorbar_opts["tick_font_color"] = styles.colorbar["tick_font_color"]
            if "bgcolor" in styles.colorbar:
                colorbar_opts["bgcolor"] = styles.colorbar["bgcolor"]
            if "bordercolor" in styles.colorbar:
                colorbar_opts["bordercolor"] = styles.colorbar["bordercolor"]
            if "borderwidth" in styles.colorbar:
                colorbar_opts["borderwidth"] = styles.colorbar["borderwidth"]
            if "len" in styles.colorbar:
                colorbar_opts["len"] = styles.colorbar["len"]
            if "thickness" in styles.colorbar:
                colorbar_opts["thickness"] = styles.colorbar["thickness"]
            if colorbar_opts:
                opts["colorbar_opts"] = colorbar_opts

        if styles.hover:
            if "mode" in styles.hover:
                opts["hovermode"] = styles.hover["mode"]

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

        if styles.hover:
            if "background_color" in styles.hover:
                opts["hover_fill_color"] = styles.hover["background_color"]
            if "alpha" in styles.hover:
                opts["hover_fill_alpha"] = styles.hover["alpha"]
            if "line_color" in styles.hover:
                opts["hover_line_color"] = styles.hover["line_color"]
            if "line_alpha" in styles.hover:
                opts["hover_line_alpha"] = styles.hover["line_alpha"]
            if "line_width" in styles.hover:
                opts["hover_line_width"] = styles.hover["line_width"]

    elif backend == "matplotlib":
        pass

    elif backend == "plotly":
        if styles.hover:
            if "background_color" in styles.hover:
                opts["hoverlabel_bgcolor"] = styles.hover["background_color"]
            if "font_size" in styles.hover:
                opts["hoverlabel_font_size"] = styles.hover["font_size"]
            if "font_family" in styles.hover:
                opts["hoverlabel_font_family"] = styles.hover["font_family"]
            if "font_color" in styles.hover:
                opts["hoverlabel_font_color"] = styles.hover["font_color"]
            if "border_color" in styles.hover:
                opts["hoverlabel_bordercolor"] = styles.hover["border_color"]
            if "border_width" in styles.hover:
                opts["hoverlabel_borderwidth"] = styles.hover["border_width"]

    return opts


def _register_builtin_themes() -> None:
    default_theme = Theme(
        name="default",
        description="The default HoloViews theme with sensible defaults.",
        styles={
            "bokeh": ThemeStyles(
                font={"family": "Helvetica", "size": "12pt"},
                grid={"show": True, "color": "#e0e0e0", "alpha": 0.8},
                background={"color": "#ffffff"},
                legend={
                    "position": "top_right",
                    "show": True,
                    "background_fill_color": "#ffffff",
                    "background_fill_alpha": 0.9,
                },
                toolbar={"position": "above", "autohide": False, "show": True},
                colorbar={
                    "show": True,
                    "background_fill_color": "#ffffff",
                },
                hover={
                    "show": True,
                    "background_color": "#ffffff",
                    "alpha": 0.95,
                },
            ),
            "matplotlib": ThemeStyles(
                font={"family": "sans-serif", "size": 12},
                grid={"show": True, "color": "#e0e0e0", "line_width": 0.5, "alpha": 0.8},
                background={"color": "#ffffff"},
                legend={
                    "position": "best",
                    "frame": True,
                    "show": True,
                    "fontsize": 10,
                    "framealpha": 0.9,
                },
                toolbar={"show": True},
                colorbar={"show": True, "labelsize": 10},
            ),
            "plotly": ThemeStyles(
                font={"family": "Arial", "size": 12},
                grid={"show": True, "color": "#e0e0e0", "width": 1},
                background={"color": "#ffffff"},
                legend={
                    "position": (1.02, 1),
                    "show": True,
                    "bgcolor": "#ffffff",
                    "borderwidth": 0,
                },
                toolbar={"show": True},
                colorbar={"show": True, "bgcolor": "#ffffff"},
                hover={"show": True, "background_color": "#ffffff"},
            ),
        },
    )

    presentation_theme = Theme(
        name="presentation",
        description="A theme optimized for presentations with larger fonts and bold styling.",
        styles={
            "bokeh": ThemeStyles(
                font={"family": "Helvetica", "size": "16pt", "style": "bold", "color": "#333333"},
                grid={"show": True, "color": "#c0c0c0", "line_width": 1.5, "alpha": 0.9},
                background={"color": "#ffffff"},
                legend={
                    "position": "top_right",
                    "click_policy": "hide",
                    "show": True,
                    "label_text_font_size": "14pt",
                    "title_text_font_size": "14pt",
                    "background_fill_color": "#ffffff",
                    "background_fill_alpha": 0.95,
                    "border_line_width": 1,
                    "padding": 10,
                    "spacing": 8,
                },
                toolbar={"position": "above", "autohide": True, "show": True},
                colorbar={
                    "show": True,
                    "title_text_font_size": "14pt",
                    "major_label_text_font_size": "12pt",
                    "background_fill_color": "#ffffff",
                },
                hover={
                    "show": True,
                    "background_color": "#f0f0f0",
                    "alpha": 0.95,
                    "line_color": "#999999",
                    "line_width": 2,
                },
            ),
            "matplotlib": ThemeStyles(
                font={"family": "sans-serif", "size": 16, "weight": "bold"},
                grid={"show": True, "color": "#c0c0c0", "line_width": 1.5, "alpha": 0.9},
                background={"color": "#ffffff"},
                legend={
                    "position": "best",
                    "frame": True,
                    "show": True,
                    "fontsize": 14,
                    "title_fontsize": 14,
                    "framealpha": 0.95,
                    "borderpad": 1.0,
                    "labelspacing": 0.8,
                },
                toolbar={"show": True},
                colorbar={
                    "show": True,
                    "labelsize": 12,
                    "pad": 0.1,
                    "shrink": 0.8,
                },
            ),
            "plotly": ThemeStyles(
                font={"family": "Arial", "size": 16, "color": "#333333"},
                grid={"show": True, "color": "#c0c0c0", "width": 2},
                background={"color": "#ffffff"},
                legend={
                    "position": (1.02, 1),
                    "show": True,
                    "font_size": 14,
                    "title_font_size": 14,
                    "bgcolor": "#ffffff",
                    "borderwidth": 1,
                    "bordercolor": "#cccccc",
                },
                toolbar={"show": True},
                colorbar={
                    "show": True,
                    "title_font_size": 14,
                    "tick_font_size": 12,
                    "bgcolor": "#ffffff",
                    "len": 0.8,
                    "thickness": 20,
                },
                hover={
                    "show": True,
                    "font_size": 14,
                    "background_color": "#f0f0f0",
                    "border_color": "#cccccc",
                    "border_width": 1,
                },
            ),
        },
    )

    dark_theme = Theme(
        name="dark",
        description="A dark theme with high contrast colors.",
        styles={
            "bokeh": ThemeStyles(
                font={"family": "Helvetica", "size": "12pt", "color": "#ffffff"},
                grid={"show": True, "color": "#404040", "alpha": 0.8},
                background={"color": "#222222", "border_color": "#333333"},
                legend={
                    "position": "top_right",
                    "show": True,
                    "label_text_color": "#ffffff",
                    "title_text_color": "#ffffff",
                    "background_fill_color": "#333333",
                    "background_fill_alpha": 0.9,
                    "border_line_color": "#555555",
                    "border_line_width": 1,
                },
                toolbar={"position": "above", "autohide": False, "show": True},
                colorbar={
                    "show": True,
                    "title_text_color": "#ffffff",
                    "major_label_text_color": "#ffffff",
                    "background_fill_color": "#333333",
                    "bar_line_color": "#555555",
                },
                hover={
                    "show": True,
                    "background_color": "#333333",
                    "line_color": "#666666",
                    "alpha": 0.95,
                },
            ),
            "matplotlib": ThemeStyles(
                font={"family": "sans-serif", "size": 12},
                grid={"show": True, "color": "#404040", "line_width": 0.5, "alpha": 0.8},
                background={"color": "#222222", "edge_color": "#444444"},
                legend={
                    "position": "best",
                    "frame": True,
                    "show": True,
                    "facecolor": "#333333",
                    "edgecolor": "#555555",
                    "label_text_color": "#ffffff",
                    "framealpha": 0.9,
                },
                toolbar={"show": True},
                colorbar={
                    "show": True,
                    "labelsize": 10,
                },
            ),
            "plotly": ThemeStyles(
                font={"family": "Arial", "size": 12, "color": "#ffffff"},
                grid={"show": True, "color": "#404040", "width": 1},
                background={"color": "#222222"},
                legend={
                    "position": (1.02, 1),
                    "show": True,
                    "font_color": "#ffffff",
                    "title_font_color": "#ffffff",
                    "bgcolor": "#333333",
                    "bordercolor": "#555555",
                    "borderwidth": 1,
                },
                toolbar={"show": True},
                colorbar={
                    "show": True,
                    "title_font_color": "#ffffff",
                    "tick_font_color": "#ffffff",
                    "bgcolor": "#333333",
                    "bordercolor": "#555555",
                },
                hover={
                    "show": True,
                    "background_color": "#333333",
                    "font_color": "#ffffff",
                    "border_color": "#555555",
                },
            ),
        },
    )

    minimal_theme = Theme(
        name="minimal",
        description="A clean, minimal theme with minimal decorations.",
        styles={
            "bokeh": ThemeStyles(
                font={"family": "Helvetica", "size": "11pt", "color": "#333333"},
                grid={"show": False},
                background={"color": "#ffffff"},
                legend={
                    "position": "top_right",
                    "show": True,
                    "background_fill_color": "#ffffff",
                    "background_fill_alpha": 0.0,
                    "border_line_width": 0,
                },
                toolbar={"position": None, "show": False},
                colorbar={
                    "show": True,
                    "background_fill_color": "#ffffff",
                    "border_line_width": 0,
                },
                hover={
                    "show": True,
                    "background_color": "#fafafa",
                    "alpha": 0.9,
                    "line_width": 1,
                },
            ),
            "matplotlib": ThemeStyles(
                font={"family": "sans-serif", "size": 11},
                grid={"show": False},
                background={"color": "#ffffff"},
                legend={
                    "position": "best",
                    "frame": False,
                    "show": True,
                    "framealpha": 0.0,
                },
                toolbar={"show": False},
                colorbar={
                    "show": True,
                    "labelsize": 10,
                },
            ),
            "plotly": ThemeStyles(
                font={"family": "Arial", "size": 11},
                grid={"show": False},
                background={"color": "#ffffff"},
                legend={
                    "position": (1.02, 1),
                    "show": True,
                    "bgcolor": "#ffffff",
                    "borderwidth": 0,
                },
                toolbar={"show": False},
                colorbar={
                    "show": True,
                    "bgcolor": "#ffffff",
                    "borderwidth": 0,
                },
                hover={
                    "show": True,
                    "background_color": "#fafafa",
                    "borderwidth": 0,
                },
            ),
        },
    )

    ggplot_theme = Theme(
        name="ggplot",
        description="A theme inspired by R's ggplot2.",
        styles={
            "bokeh": ThemeStyles(
                font={"family": "Helvetica", "size": "12pt"},
                grid={"show": True, "color": "#ffffff", "line_width": 1.5, "alpha": 1.0},
                background={"color": "#ebebeb"},
                legend={
                    "position": "top_right",
                    "show": True,
                    "background_fill_color": "#ffffff",
                    "border_line_color": "#cccccc",
                    "border_line_width": 1,
                },
                toolbar={"position": "above", "show": True},
                colorbar={
                    "show": True,
                    "background_fill_color": "#ffffff",
                    "border_line_color": "#cccccc",
                },
                hover={
                    "show": True,
                    "background_color": "#ffffff",
                    "alpha": 0.95,
                },
            ),
            "matplotlib": ThemeStyles(
                font={"family": "sans-serif", "size": 12},
                grid={"show": True, "color": "#ffffff", "line_width": 1.5},
                background={"color": "#ebebeb"},
                legend={
                    "position": "best",
                    "frame": True,
                    "show": True,
                    "facecolor": "#ffffff",
                    "edgecolor": "#cccccc",
                    "framealpha": 1.0,
                },
                toolbar={"show": True},
                colorbar={
                    "show": True,
                    "labelsize": 10,
                },
            ),
            "plotly": ThemeStyles(
                font={"family": "Arial", "size": 12},
                grid={"show": True, "color": "#ffffff", "width": 2},
                background={"color": "#ebebeb"},
                legend={
                    "position": (1.02, 1),
                    "show": True,
                    "bgcolor": "#ffffff",
                    "bordercolor": "#cccccc",
                    "borderwidth": 1,
                },
                toolbar={"show": True},
                colorbar={
                    "show": True,
                    "bgcolor": "#ffffff",
                    "bordercolor": "#cccccc",
                    "borderwidth": 1,
                },
                hover={
                    "show": True,
                    "background_color": "#ffffff",
                    "border_color": "#cccccc",
                },
            ),
        },
    )

    for theme in [default_theme, presentation_theme, dark_theme, minimal_theme, ggplot_theme]:
        theme_registry.register(theme)


_register_builtin_themes()
