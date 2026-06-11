from __future__ import annotations

import logging
import typing as t
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import local

if t.TYPE_CHECKING:
    from .options import Options

logger = logging.getLogger("holoviews.theme")

_BACKEND_T = t.Literal["bokeh", "matplotlib", "plotly"]
_BACKENDS: tuple[_BACKEND_T, ...] = ("bokeh", "matplotlib", "plotly")

_STYLE_CATEGORY = t.Literal[
    "font", "grid", "background", "legend", "toolbar", "colorbar", "hover"
]


class ThemeCapabilities:
    """Describe what theme capabilities each backend supports.

    Each entry maps a style category (e.g. 'font') to the list of
    sub-keys that are actually rendered by the backend.  Keys that are
    **not** listed here are either ignored explicitly or downgraded to
    a closest equivalent - never silently dropped.
    """

    BOKEH: dict[_STYLE_CATEGORY, list[str]] = {
        "font": ["family", "size", "style", "color"],
        "grid": ["show", "xaxis", "yaxis", "color", "alpha", "line_width", "linestyle"],
        "background": ["color", "border_color"],
        "legend": [
            "position", "click_policy", "show", "cols", "muted",
            "label_text_font_size", "label_text_font", "label_text_color",
            "title_text_font_size", "title_text_font", "title_text_color",
            "background_fill_color", "background_fill_alpha",
            "border_line_color", "border_line_alpha", "border_line_width",
            "spacing", "padding",
        ],
        "toolbar": ["position", "autohide", "show"],
        "colorbar": [
            "show", "position",
            "title_text_font_size", "title_text_font", "title_text_color",
            "major_label_text_font_size", "major_label_text_font", "major_label_text_color",
            "background_fill_color", "border_line_color", "bar_line_color", "scale_alpha",
        ],
        "hover": ["tooltips", "mode", "show", "background_color", "alpha", "line_color", "line_width"],
    }

    MATPLOTLIB: dict[_STYLE_CATEGORY, list[str]] = {
        "font": ["family", "size", "weight"],
        "grid": ["show", "color", "alpha", "line_width", "linestyle"],
        "background": ["color", "edge_color"],
        "legend": [
            "position", "frame", "show", "fontsize", "title_fontsize",
            "framealpha", "edgecolor", "facecolor", "borderpad", "labelspacing",
        ],
        "toolbar": ["show"],
        "colorbar": ["show", "labelsize", "pad", "shrink", "aspect", "fraction"],
        "hover": [],
    }

    PLOTLY: dict[_STYLE_CATEGORY, list[str]] = {
        "font": ["family", "size", "color"],
        "grid": ["show", "color", "width"],
        "background": ["color"],
        "legend": [
            "position", "orientation", "show",
            "font_size", "font_family", "font_color",
            "bgcolor", "bordercolor", "borderwidth",
            "title_font_size", "title_font_family", "title_font_color",
        ],
        "toolbar": [],
        "colorbar": [
            "show",
            "title_font_size", "title_font_family", "title_font_color",
            "tick_font_size", "tick_font_family", "tick_font_color",
            "bgcolor", "bordercolor", "borderwidth", "len", "thickness",
        ],
        "hover": [
            "mode",
            "background_color", "font_size", "font_family", "font_color",
            "border_color", "border_width",
        ],
    }

    @classmethod
    def for_backend(cls, backend: _BACKEND_T) -> dict[_STYLE_CATEGORY, list[str]]:
        mapping = {
            "bokeh": cls.BOKEH,
            "matplotlib": cls.MATPLOTLIB,
            "plotly": cls.PLOTLY,
        }
        return mapping[backend]

    @classmethod
    def filter_styles(
        cls,
        styles: "ThemeStyles",
        backend: _BACKEND_T,
        warn: bool = True,
    ) -> "ThemeStyles":
        """Return a copy of *styles* keeping only keys the backend supports.

        Unsupported keys are logged so that the user is aware of
        degradation - nothing is ever silently dropped.
        """
        caps = cls.for_backend(backend)
        filtered_kwargs: dict[str, dict[str, t.Any]] = {}
        for category in ThemeStyles.__dataclass_fields__:
            category = t.cast(_STYLE_CATEGORY, category)
            raw = getattr(styles, category)
            allowed = caps.get(category, [])
            supported = {k: v for k, v in raw.items() if k in allowed}
            dropped = [k for k in raw if k not in allowed]
            if dropped and warn:
                logger.info(
                    "Theme capability downgrade on %s: category=%r dropped keys=%s",
                    backend, category, dropped,
                )
            filtered_kwargs[category] = supported
        return ThemeStyles(**filtered_kwargs)


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
    raw = theme.get_styles(backend)
    styles = ThemeCapabilities.filter_styles(raw, backend)
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


# ---------------------------------------------------------------------------
# Direct application helpers – used by the plotting backends at the actual
# rendering points, so that themes are never "filtered out" before reaching
# the underlying toolkit.
# ---------------------------------------------------------------------------

_STYLE_CATEGORY = t.Literal[
    "font", "grid", "background", "legend", "toolbar", "colorbar", "hover"
]

UserKeysDict = dict[_STYLE_CATEGORY, set[str]]


def _merge_user_keys(
    a: UserKeysDict, b: UserKeysDict
) -> UserKeysDict:
    merged: UserKeysDict = {
        "font": set(), "grid": set(), "background": set(),
        "legend": set(), "toolbar": set(), "colorbar": set(), "hover": set(),
    }
    for cat in merged:
        merged[cat] = a.get(cat, set()) | b.get(cat, set())
    return merged


# Mapping from HoloViews param/opt names -> ThemeStyles category and key.
# Used to translate user opts into "which theme keys are already set by user"
_OPT_TO_THEME_KEY: dict[str, tuple[_STYLE_CATEGORY, str]] = {
    # -- font / title --
    "fontsize": ("font", "size"),
    "title": ("font", "title"),
    "title_format": ("font", "title_format"),
    # -- axes font is implicit via fontsize --
    # -- background --
    "bgcolor": ("background", "color"),
    "show_frame": ("background", "show_frame"),
    "border": ("background", "border_color"),
    # -- grid --
    "show_grid": ("grid", "show"),
    "gridstyle": ("grid", "gridstyle"),
    "xgrid": ("grid", "xaxis"),
    "ygrid": ("grid", "yaxis"),
    "show_xgrid": ("grid", "xaxis"),
    "show_ygrid": ("grid", "yaxis"),
    # -- toolbar --
    "toolbar": ("toolbar", "position"),
    "autohide_toolbar": ("toolbar", "autohide"),
    # -- legend --
    "legend_position": ("legend", "position"),
    "legend_offset": ("legend", "offset"),
    "legend_cols": ("legend", "ncol"),
    "legend_muted": ("legend", "muted"),
    "show_legend": ("legend", "show"),
    "legend_opts": ("legend", "__opts_dict__"),
    # -- colorbar --
    "colorbar": ("colorbar", "show"),
    "colorbar_opts": ("colorbar", "__opts_dict__"),
    "colorbar_position": ("colorbar", "position"),
    "clabel": ("colorbar", "label"),
    "cformatter": ("colorbar", "formatter"),
    "cticks": ("colorbar", "ticks"),
    # -- hover --
    "hover_tooltips": ("hover", "tooltips"),
    "hover": ("hover", "mode"),
}


def _collect_user_keys_from_opts(
    kwargs: dict[str, t.Any],
    opts_dict_name: str | None,
    target_cat: _STYLE_CATEGORY,
) -> set[str]:
    """Pull user-set keys out of ``kwargs`` or a nested opts dict (e.g. legend_opts)."""
    keys: set[str] = set()
    if opts_dict_name and opts_dict_name in kwargs:
        keys |= set(kwargs[opts_dict_name].keys())
    return keys


def get_user_explicit_keys(plot, backend: _BACKEND_T) -> UserKeysDict:
    """Return the set of theme-style keys the user has already set via ``.opts()``.

    The result is grouped by ThemeStyles category.  A theme helper should
    **never** fill in a key that is present in this set — doing so would
    overwrite an explicit user choice.
    """
    user_keys: UserKeysDict = {
        "font": set(), "grid": set(), "background": set(),
        "legend": set(), "toolbar": set(), "colorbar": set(), "hover": set(),
    }

    # Try to locate the underlying HoloViews element from the plot.
    element = None
    for attr in ("hmap",):
        if hasattr(plot, attr):
            hmap = getattr(plot, attr)
            if hasattr(hmap, "last"):
                element = hmap.last
                break
    if element is None and hasattr(plot, "current_frame"):
        element = plot.current_frame
    if element is None:
        return user_keys

    from .options import Store

    for group in ("plot", "style"):
        try:
            opts = Store.lookup_options(backend, element, group, defaults=False)
        except Exception:
            continue
        if not opts:
            continue

        for k, v in opts.kwargs.items():
            if k in _OPT_TO_THEME_KEY:
                cat, theme_key = _OPT_TO_THEME_KEY[k]
                if theme_key == "__opts_dict__":
                    if isinstance(v, dict):
                        user_keys[cat] |= set(v.keys())
                else:
                    user_keys[cat].add(theme_key)

    # Also check legend_opts / colorbar_opts params directly on the plot
    # instance, which may have been supplied via .opts() without going
    # through the registry.
    if hasattr(plot, "legend_opts"):
        for attr in ("legend_opts",):
            val = getattr(plot, attr, None)
            if isinstance(val, dict) and val:
                # legend_opts contains Bokeh Legend attribute names; map common ones
                for lk in val:
                    user_keys["legend"].add(lk)
    if hasattr(plot, "colorbar_opts"):
        val = getattr(plot, "colorbar_opts", None)
        if isinstance(val, dict) and val:
            for ck in val:
                user_keys["colorbar"].add(ck)

    return user_keys


def get_theme_styles_for_plot(
    obj, backend: _BACKEND_T
) -> tuple[ThemeStyles, UserKeysDict]:
    """Resolve the effective theme for a plot object and return its styles
    **and** the set of keys the user already set explicitly via ``.opts()``.

    Priority order (highest first):
      1. per-object theme (``.opts(theme=...)``)
      2. innermost ``with hv.opts.theme(...)`` context
      3. global default set via ``hv.opts.defaults_theme(...)``
    """
    from .options import _get_object_theme

    theme = _get_object_theme(obj) or get_active_theme()
    user_keys = get_user_explicit_keys(obj, backend)
    if theme is None:
        return ThemeStyles(), user_keys
    raw = theme.get_styles(backend)
    styles = ThemeCapabilities.filter_styles(raw, backend)
    return styles, user_keys


# --- Bokeh -----------------------------------------------------------------

_BOKEH_ATTR_TO_THEME_KEY: dict[str, tuple[_STYLE_CATEGORY, str]] = {
    # figure
    "background_fill_color": ("background", "color"),
    "border_fill_color": ("background", "border_color"),
    "toolbar_location": ("toolbar", "position"),
    # title
    "text_font": ("font", "family"),
    "text_font_size": ("font", "size"),
    "text_font_style": ("font", "style"),
    "text_color": ("font", "color"),
    # axes
    "axis_label_text_font": ("font", "family"),
    "major_label_text_font": ("font", "family"),
    "axis_label_text_font_size": ("font", "size"),
    "major_label_text_font_size": ("font", "size"),
    "axis_label_text_font_style": ("font", "style"),
    "axis_label_text_color": ("font", "color"),
    "major_label_text_color": ("font", "color"),
    # grid
    "grid_line_color": ("grid", "color"),
    "grid_line_alpha": ("grid", "alpha"),
    "grid_line_width": ("grid", "line_width"),
    "grid_line_dash": ("grid", "linestyle"),
    # toolbar
    "autohide": ("toolbar", "autohide"),
    # legend
    "label_text_font_size": ("legend", "font_size"),
    "label_text_font": ("legend", "font_family"),
    "label_text_color": ("legend", "font_color"),
    "title_text_font_size": ("legend", "title_font_size"),
    "title_text_font": ("legend", "title_font_family"),
    "title_text_color": ("legend", "title_font_color"),
    "background_fill_color": ("legend", "bgcolor"),
    "border_line_color": ("legend", "bordercolor"),
    "border_line_width": ("legend", "borderwidth"),
    "border_line_alpha": ("legend", "borderalpha"),
    "label_standoff": ("legend", "labelspacing"),
    "padding": ("legend", "padding"),
    "spacing": ("legend", "spacing"),
    "margin": ("legend", "margins"),
    "visible": ("legend", "show"),
    # colorbar
    "title_text_font_size": ("colorbar", "title_font_size"),
    "title_text_font": ("colorbar", "title_font_family"),
    "title_text_color": ("colorbar", "title_font_color"),
    "major_label_text_font_size": ("colorbar", "tick_font_size"),
    "major_label_text_font": ("colorbar", "tick_font_family"),
    "major_label_text_color": ("colorbar", "tick_font_color"),
    "background_fill_color": ("colorbar", "bgcolor"),
    "bar_line_color": ("colorbar", "bordercolor"),
    "bar_line_width": ("colorbar", "borderwidth"),
    "bar_line_alpha": ("colorbar", "bar_alpha"),
    "title_standoff": ("colorbar", "label_standoff"),
    "major_tick_line_color": ("colorbar", "major_tick_line_color"),
    "minor_tick_line_color": ("colorbar", "minor_tick_line_color"),
    # hover
    "background": ("hover", "background_color"),
    "border_line_color": ("hover", "border_color"),
    "mode": ("hover", "mode"),
}


def _bokeh_setdefault(
    model,
    attr: str,
    value: t.Any,
    user_keys: UserKeysDict | None = None,
) -> bool:
    """Set ``model.attr = value`` **only if** the user hasn't set it explicitly.

    The check uses two sources of truth:
      1. ``user_keys`` – the set of theme-style category keys the user
         touched via ``.opts()`` (the ground truth).
      2. ``properties_with_values(include_defaults=False)`` – a safety net
         that catches any non-default value on the model itself.

    Returns ``True`` if the value was written, ``False`` otherwise.
    """
    cat_key = _BOKEH_ATTR_TO_THEME_KEY.get(attr)
    if cat_key is not None and user_keys is not None:
        cat, theme_key = cat_key
        if theme_key in user_keys.get(cat, set()):
            return False

    non_defaults = model.properties_with_values(include_defaults=False)
    if attr in non_defaults:
        return False
    setattr(model, attr, value)
    return True


def apply_bokeh_theme_to_figure(
    plot,
    styles: ThemeStyles,
    user_keys: UserKeysDict | None = None,
) -> None:
    """Apply *styles* to an already-created Bokeh ``Figure``.

    Uses :func:`_bokeh_setdefault` everywhere so user-``.opts()`` values
    are **never** overridden by the theme.
    """
    if not styles:
        return
    uk = user_keys

    # --- background ------------------------------------------------------
    if styles.background:
        if "color" in styles.background:
            _bokeh_setdefault(plot, "background_fill_color", styles.background["color"], uk)
            _bokeh_setdefault(plot, "background_fill_alpha", None, uk)
        if "border_color" in styles.background:
            _bokeh_setdefault(plot, "border_fill_color", styles.background["border_color"], uk)

    # --- font / title ---------------------------------------------------
    if styles.font and plot.title:
        if "family" in styles.font:
            _bokeh_setdefault(plot.title, "text_font", styles.font["family"], uk)
        if "size" in styles.font:
            sz = (str(styles.font["size"]) + "pt"
                  if isinstance(styles.font["size"], int) else styles.font["size"])
            _bokeh_setdefault(plot.title, "text_font_size", sz, uk)
        if "style" in styles.font:
            _bokeh_setdefault(plot.title, "text_font_style", styles.font["style"], uk)
        if "color" in styles.font:
            _bokeh_setdefault(plot.title, "text_color", styles.font["color"], uk)

    # --- axes ------------------------------------------------------------
    if styles.font:
        for axis in list(plot.xaxis) + list(plot.yaxis):
            if "family" in styles.font:
                _bokeh_setdefault(axis, "axis_label_text_font", styles.font["family"], uk)
                _bokeh_setdefault(axis, "major_label_text_font", styles.font["family"], uk)
            if "size" in styles.font:
                sz = (str(styles.font["size"]) + "pt"
                      if isinstance(styles.font["size"], int) else styles.font["size"])
                _bokeh_setdefault(axis, "axis_label_text_font_size", sz, uk)
                _bokeh_setdefault(axis, "major_label_text_font_size", sz, uk)
            if "style" in styles.font:
                _bokeh_setdefault(axis, "axis_label_text_font_style", styles.font["style"], uk)
            if "color" in styles.font:
                _bokeh_setdefault(axis, "axis_label_text_color", styles.font["color"], uk)
                _bokeh_setdefault(axis, "major_label_text_color", styles.font["color"], uk)

    # --- grid ------------------------------------------------------------
    if styles.grid:
        grid_updates_x, grid_updates_y = {}, {}
        if "show" in styles.grid and not styles.grid["show"]:
            grid_updates_x["grid_line_color"] = None
            grid_updates_y["grid_line_color"] = None
        else:
            if "color" in styles.grid:
                grid_updates_x["grid_line_color"] = styles.grid["color"]
                grid_updates_y["grid_line_color"] = styles.grid["color"]
            if "alpha" in styles.grid:
                grid_updates_x["grid_line_alpha"] = styles.grid["alpha"]
                grid_updates_y["grid_line_alpha"] = styles.grid["alpha"]
            if "line_width" in styles.grid:
                grid_updates_x["grid_line_width"] = styles.grid["line_width"]
                grid_updates_y["grid_line_width"] = styles.grid["line_width"]
            if "linestyle" in styles.grid:
                grid_updates_x["grid_line_dash"] = styles.grid["linestyle"]
                grid_updates_y["grid_line_dash"] = styles.grid["linestyle"]
        for g in plot.xgrid:
            non_defaults = g.properties_with_values(include_defaults=False)
            apply_x = {}
            for k, v in grid_updates_x.items():
                if k in non_defaults:
                    continue
                cat_key = _BOKEH_ATTR_TO_THEME_KEY.get(k)
                if cat_key and uk and cat_key[1] in uk.get(cat_key[0], set()):
                    continue
                apply_x[k] = v
            if apply_x:
                g.update(**apply_x)
        for g in plot.ygrid:
            non_defaults = g.properties_with_values(include_defaults=False)
            apply_y = {}
            for k, v in grid_updates_y.items():
                if k in non_defaults:
                    continue
                cat_key = _BOKEH_ATTR_TO_THEME_KEY.get(k)
                if cat_key and uk and cat_key[1] in uk.get(cat_key[0], set()):
                    continue
                apply_y[k] = v
            if apply_y:
                g.update(**apply_y)

    # --- toolbar ---------------------------------------------------------
    if styles.toolbar and plot.toolbar is not None:
        if "autohide" in styles.toolbar:
            _bokeh_setdefault(plot.toolbar, "autohide", styles.toolbar["autohide"], uk)
        if "show" in styles.toolbar and not styles.toolbar["show"]:
            if "toolbar_location" not in plot.properties_with_values(include_defaults=False):
                if not (uk and "position" in uk.get("toolbar", set())):
                    plot.toolbar_location = None


def apply_bokeh_theme_to_legend(
    legend,
    styles: ThemeStyles,
    user_keys: UserKeysDict | None = None,
) -> None:
    """Apply *styles.legend* to a single Bokeh ``Legend``, defaults-only."""
    if not styles or not styles.legend:
        return
    ls = styles.legend
    mappings = {
        "font_size": ("label_text_font_size",),
        "font_family": ("label_text_font",),
        "font_color": ("label_text_color",),
        "title_font_size": ("title_text_font_size",),
        "title_font_family": ("title_text_font",),
        "title_font_color": ("title_text_color",),
        "bgcolor": ("background_fill_color",),
        "bordercolor": ("border_line_color",),
        "borderwidth": ("border_line_width",),
        "borderalpha": ("border_line_alpha",),
        "labelspacing": ("label_standoff",),
        "padding": ("padding",),
        "spacing": ("spacing",),
        "margins": ("margin",),
    }
    for theme_key, bokeh_attrs in mappings.items():
        if theme_key not in ls:
            continue
        val = ls[theme_key]
        if theme_key.endswith("_font_size") and isinstance(val, int):
            val = f"{val}pt"
        elif theme_key == "font_size" and isinstance(val, int):
            val = f"{val}pt"
        for attr in bokeh_attrs:
            _bokeh_setdefault(legend, attr, val, user_keys)
    if "frame" in ls and not ls["frame"]:
        _bokeh_setdefault(legend, "border_line_alpha", 0, user_keys)
        _bokeh_setdefault(legend, "background_fill_alpha", 0, user_keys)
    if "show" in ls and not ls["show"]:
        _bokeh_setdefault(legend, "visible", False, user_keys)


def apply_bokeh_theme_to_colorbar(
    color_bar,
    styles: ThemeStyles,
    user_keys: UserKeysDict | None = None,
) -> None:
    """Apply *styles.colorbar* to a single Bokeh ``ColorBar``, defaults-only."""
    if not styles or not styles.colorbar:
        return
    cb = styles.colorbar
    mappings = {
        "title_font_size": ("title_text_font_size",),
        "title_font_family": ("title_text_font",),
        "title_font_color": ("title_text_color",),
        "tick_font_size": ("major_label_text_font_size",),
        "tick_font_family": ("major_label_text_font",),
        "tick_font_color": ("major_label_text_color",),
        "bgcolor": ("background_fill_color",),
        "bordercolor": ("bar_line_color",),
        "borderwidth": ("bar_line_width",),
        "padding": ("padding",),
        "bar_alpha": ("bar_line_alpha",),
        "label_standoff": ("title_standoff",),
        "major_tick_line_color": ("major_tick_line_color",),
        "minor_tick_line_color": ("minor_tick_line_color",),
    }
    for theme_key, bokeh_attrs in mappings.items():
        if theme_key not in cb:
            continue
        val = cb[theme_key]
        if theme_key.endswith("_font_size") and isinstance(val, int):
            val = f"{val}pt"
        for attr in bokeh_attrs:
            _bokeh_setdefault(color_bar, attr, val, user_keys)
    if "show" in cb and not cb["show"]:
        _bokeh_setdefault(color_bar, "visible", False, user_keys)


def apply_bokeh_theme_to_hover(
    hover_tool,
    styles: ThemeStyles,
    user_keys: UserKeysDict | None = None,
) -> None:
    """Apply *styles.hover* styling to a Bokeh ``HoverTool``, defaults-only."""
    if not styles or not styles.hover:
        return
    hs = styles.hover
    if "background_color" in hs:
        _bokeh_setdefault(hover_tool, "background", hs["background_color"], user_keys)
    if "border_color" in hs:
        _bokeh_setdefault(hover_tool, "border_line_color", hs["border_color"], user_keys)
    if "mode" in hs:
        _bokeh_setdefault(hover_tool, "mode", hs["mode"], user_keys)


# --- Matplotlib -----------------------------------------------------------

_MPL_RCPARAM_TO_THEME_KEY: dict[str, tuple[_STYLE_CATEGORY, str]] = {
    "font.family": ("font", "family"),
    "font.size": ("font", "size"),
    "font.weight": ("font", "weight"),
    "figure.facecolor": ("background", "color"),
    "axes.facecolor": ("background", "color"),
    "axes.edgecolor": ("background", "edge_color"),
    "axes.grid": ("grid", "show"),
    "grid.color": ("grid", "color"),
    "grid.alpha": ("grid", "alpha"),
    "grid.linewidth": ("grid", "line_width"),
    "grid.linestyle": ("grid", "linestyle"),
    "legend.fontsize": ("legend", "fontsize"),
    "legend.title_fontsize": ("legend", "title_fontsize"),
    "legend.framealpha": ("legend", "framealpha"),
    "legend.edgecolor": ("legend", "edgecolor"),
    "legend.facecolor": ("legend", "facecolor"),
    "legend.borderpad": ("legend", "borderpad"),
    "legend.labelspacing": ("legend", "labelspacing"),
    "legend.frameon": ("legend", "frame"),
    "toolbar": ("toolbar", "show"),
}


def apply_matplotlib_theme_to_rcparams(
    styles: ThemeStyles,
    user_keys: UserKeysDict | None = None,
) -> dict[str, t.Any]:
    """Return an ``rcParams``-style dictionary derived from *styles*.

    Only keys that the user did **not** set explicitly via ``.opts()``
    (tracked in *user_keys*) are included in the result.
    """
    rc: dict[str, t.Any] = {}
    if not styles:
        return rc

    def _ok(rc_key: str) -> bool:
        if user_keys is None:
            return True
        cat_key = _MPL_RCPARAM_TO_THEME_KEY.get(rc_key)
        if cat_key is None:
            return True
        cat, theme_key = cat_key
        return theme_key not in user_keys.get(cat, set())

    if styles.font:
        if "family" in styles.font and _ok("font.family"):
            rc["font.family"] = styles.font["family"]
        if "size" in styles.font and _ok("font.size"):
            rc["font.size"] = styles.font["size"]
        if "weight" in styles.font and _ok("font.weight"):
            rc["font.weight"] = styles.font["weight"]

    if styles.background:
        if "color" in styles.background:
            if _ok("figure.facecolor"):
                rc["figure.facecolor"] = styles.background["color"]
            if _ok("axes.facecolor"):
                rc["axes.facecolor"] = styles.background["color"]
        if "edge_color" in styles.background and _ok("axes.edgecolor"):
            rc["axes.edgecolor"] = styles.background["edge_color"]

    if styles.grid:
        if "show" in styles.grid and _ok("axes.grid"):
            rc["axes.grid"] = styles.grid["show"]
        if "color" in styles.grid and _ok("grid.color"):
            rc["grid.color"] = styles.grid["color"]
        if "alpha" in styles.grid and _ok("grid.alpha"):
            rc["grid.alpha"] = styles.grid["alpha"]
        if "line_width" in styles.grid and _ok("grid.linewidth"):
            rc["grid.linewidth"] = styles.grid["line_width"]
        if "linestyle" in styles.grid and _ok("grid.linestyle"):
            rc["grid.linestyle"] = styles.grid["linestyle"]

    if styles.legend:
        if "fontsize" in styles.legend and _ok("legend.fontsize"):
            rc["legend.fontsize"] = styles.legend["fontsize"]
        if "title_fontsize" in styles.legend and _ok("legend.title_fontsize"):
            rc["legend.title_fontsize"] = styles.legend["title_fontsize"]
        if "framealpha" in styles.legend and _ok("legend.framealpha"):
            rc["legend.framealpha"] = styles.legend["framealpha"]
        if "edgecolor" in styles.legend and _ok("legend.edgecolor"):
            rc["legend.edgecolor"] = styles.legend["edgecolor"]
        if "facecolor" in styles.legend and _ok("legend.facecolor"):
            rc["legend.facecolor"] = styles.legend["facecolor"]
        if "borderpad" in styles.legend and _ok("legend.borderpad"):
            rc["legend.borderpad"] = styles.legend["borderpad"]
        if "labelspacing" in styles.legend and _ok("legend.labelspacing"):
            rc["legend.labelspacing"] = styles.legend["labelspacing"]
        if "frame" in styles.legend and _ok("legend.frameon"):
            rc["legend.frameon"] = styles.legend["frame"]

    if styles.toolbar:
        if "show" in styles.toolbar and _ok("toolbar"):
            rc["toolbar"] = "toolbar2" if styles.toolbar["show"] else "None"

    return rc


def apply_matplotlib_theme_to_axes(
    ax,
    styles: ThemeStyles,
    user_keys: UserKeysDict | None = None,
) -> None:
    """Apply theme styles directly to a Matplotlib ``Axes``."""
    if not styles:
        return
    if styles.legend and "show" in styles.legend and not styles.legend["show"]:
        if user_keys is None or "show" not in user_keys.get("legend", set()):
            legend = ax.get_legend()
            if legend is not None:
                legend.remove()


# --- Plotly ----------------------------------------------------------------

def apply_plotly_theme_to_layout(
    layout: dict[str, t.Any],
    styles: ThemeStyles,
    xaxis: dict[str, t.Any] | None = None,
    yaxis: dict[str, t.Any] | None = None,
    user_keys: UserKeysDict | None = None,
) -> None:
    """Merge theme *styles* into a Plotly ``layout`` dict in place — **defaults only**.

    The ground truth for whether a key may be overwritten is *user_keys*,
    a set of theme-style category keys the user set via ``.opts()``.
    ``dict.setdefault`` is used on top so backend-populated defaults are
    never touched either.
    """
    if not styles:
        return

    def _ok(cat: _STYLE_CATEGORY, theme_key: str) -> bool:
        if user_keys is None:
            return True
        return theme_key not in user_keys.get(cat, set())

    def _setdefault(d: dict, k: str, v: t.Any, cat: _STYLE_CATEGORY, tk: str) -> None:
        if k not in d and _ok(cat, tk):
            d[k] = v

    # --- font ------------------------------------------------------------
    if styles.font:
        font = layout.setdefault("font", {})
        if "family" in styles.font:
            _setdefault(font, "family", styles.font["family"], "font", "family")
        if "size" in styles.font:
            _setdefault(font, "size", styles.font["size"], "font", "size")
        if "color" in styles.font:
            _setdefault(font, "color", styles.font["color"], "font", "color")

    # --- background -----------------------------------------------------
    if styles.background:
        if "color" in styles.background:
            _setdefault(layout, "paper_bgcolor", styles.background["color"], "background", "color")
            _setdefault(layout, "plot_bgcolor", styles.background["color"], "background", "color")

    # --- grid / axes ----------------------------------------------------
    if styles.grid and xaxis is not None:
        if "show" in styles.grid:
            _setdefault(xaxis, "showgrid", styles.grid["show"], "grid", "show")
            if yaxis is not None:
                _setdefault(yaxis, "showgrid", styles.grid["show"], "grid", "show")
        if "color" in styles.grid:
            _setdefault(xaxis, "gridcolor", styles.grid["color"], "grid", "color")
            if yaxis is not None:
                _setdefault(yaxis, "gridcolor", styles.grid["color"], "grid", "color")
        if "width" in styles.grid:
            _setdefault(xaxis, "gridwidth", styles.grid["width"], "grid", "line_width")
            if yaxis is not None:
                _setdefault(yaxis, "gridwidth", styles.grid["width"], "grid", "line_width")

    # --- font on axes --------------------------------------------------
    if styles.font:
        if xaxis is not None:
            xf = xaxis.setdefault("titlefont", {})
            xtf = xaxis.setdefault("tickfont", {})
            if "family" in styles.font:
                _setdefault(xf, "family", styles.font["family"], "font", "family")
                _setdefault(xtf, "family", styles.font["family"], "font", "family")
            if "size" in styles.font:
                _setdefault(xf, "size", styles.font["size"], "font", "size")
                _setdefault(xtf, "size", styles.font["size"], "font", "size")
            if "color" in styles.font:
                _setdefault(xf, "color", styles.font["color"], "font", "color")
                _setdefault(xtf, "color", styles.font["color"], "font", "color")
        if yaxis is not None:
            yf = yaxis.setdefault("titlefont", {})
            ytf = yaxis.setdefault("tickfont", {})
            if "family" in styles.font:
                _setdefault(yf, "family", styles.font["family"], "font", "family")
                _setdefault(ytf, "family", styles.font["family"], "font", "family")
            if "size" in styles.font:
                _setdefault(yf, "size", styles.font["size"], "font", "size")
                _setdefault(ytf, "size", styles.font["size"], "font", "size")
            if "color" in styles.font:
                _setdefault(yf, "color", styles.font["color"], "font", "color")
                _setdefault(ytf, "color", styles.font["color"], "font", "color")

    # --- legend ---------------------------------------------------------
    if styles.legend:
        legend = layout.setdefault("legend", {})
        if "position" in styles.legend:
            pos = styles.legend["position"]
            if isinstance(pos, tuple):
                _setdefault(legend, "x", pos[0], "legend", "position")
                _setdefault(legend, "y", pos[1], "legend", "position")
            elif isinstance(pos, str):
                _plotly_legend_position_shortcuts = {
                    "top_right": {"x": 1.02, "y": 1},
                    "top_left": {"x": -0.1, "y": 1},
                    "bottom_right": {"x": 1.02, "y": 0},
                    "bottom_left": {"x": -0.1, "y": 0},
                    "right": {"x": 1.02, "y": 0.5},
                    "left": {"x": -0.1, "y": 0.5},
                    "top": {"x": 0.5, "y": 1.1},
                    "bottom": {"x": 0.5, "y": -0.1},
                }
                if pos in _plotly_legend_position_shortcuts:
                    shortcut = _plotly_legend_position_shortcuts[pos]
                    _setdefault(legend, "x", shortcut["x"], "legend", "position")
                    _setdefault(legend, "y", shortcut["y"], "legend", "position")
        if "orientation" in styles.legend:
            _setdefault(legend, "orientation", styles.legend["orientation"], "legend", "orientation")
        if "show" in styles.legend:
            _setdefault(legend, "visible", styles.legend["show"], "legend", "show")
        if "bgcolor" in styles.legend:
            _setdefault(legend, "bgcolor", styles.legend["bgcolor"], "legend", "bgcolor")
        if "bordercolor" in styles.legend:
            _setdefault(legend, "bordercolor", styles.legend["bordercolor"], "legend", "bordercolor")
        if "borderwidth" in styles.legend:
            _setdefault(legend, "borderwidth", styles.legend["borderwidth"], "legend", "borderwidth")
        if any(k in styles.legend for k in ("font_size", "font_family", "font_color")):
            lf = legend.setdefault("font", {})
            if "font_size" in styles.legend:
                _setdefault(lf, "size", styles.legend["font_size"], "legend", "font_size")
            if "font_family" in styles.legend:
                _setdefault(lf, "family", styles.legend["font_family"], "legend", "font_family")
            if "font_color" in styles.legend:
                _setdefault(lf, "color", styles.legend["font_color"], "legend", "font_color")
        if any(k in styles.legend for k in ("title_font_size", "title_font_family", "title_font_color")):
            title = legend.setdefault("title", {})
            tf = title.setdefault("font", {})
            if "title_font_size" in styles.legend:
                _setdefault(tf, "size", styles.legend["title_font_size"], "legend", "title_font_size")
            if "title_font_family" in styles.legend:
                _setdefault(tf, "family", styles.legend["title_font_family"], "legend", "title_font_family")
            if "title_font_color" in styles.legend:
                _setdefault(tf, "color", styles.legend["title_font_color"], "legend", "title_font_color")

    # --- hover ---------------------------------------------------------
    if styles.hover:
        if "mode" in styles.hover:
            _setdefault(layout, "hovermode", styles.hover["mode"], "hover", "mode")
        hl = layout.setdefault("hoverlabel", {})
        if "background_color" in styles.hover:
            _setdefault(hl, "bgcolor", styles.hover["background_color"], "hover", "background_color")
        if "border_color" in styles.hover:
            _setdefault(hl, "bordercolor", styles.hover["border_color"], "hover", "border_color")
        if "border_width" in styles.hover:
            _setdefault(hl, "borderwidth", styles.hover["border_width"], "hover", "border_width")
        if any(k in styles.hover for k in ("font_size", "font_family", "font_color")):
            hf = hl.setdefault("font", {})
            if "font_size" in styles.hover:
                _setdefault(hf, "size", styles.hover["font_size"], "hover", "font_size")
            if "font_family" in styles.hover:
                _setdefault(hf, "family", styles.hover["font_family"], "hover", "font_family")
            if "font_color" in styles.hover:
                _setdefault(hf, "color", styles.hover["font_color"], "hover", "font_color")


def apply_plotly_theme_to_trace(
    trace: dict[str, t.Any],
    styles: ThemeStyles,
    user_keys: UserKeysDict | None = None,
) -> None:
    """Merge theme *styles* into a single Plotly trace dictionary — **defaults only**."""
    if not styles:
        return

    def _ok(cat: _STYLE_CATEGORY, theme_key: str) -> bool:
        if user_keys is None:
            return True
        return theme_key not in user_keys.get(cat, set())

    def _setdefault(d: dict, k: str, v: t.Any, cat: _STYLE_CATEGORY, tk: str) -> None:
        if k not in d and _ok(cat, tk):
            d[k] = v

    # colorbar lives on the trace
    if styles.colorbar:
        cb = trace.setdefault("colorbar", {})
        if "title_font_size" in styles.colorbar:
            tf = cb.setdefault("title", {}).setdefault("font", {})
            _setdefault(tf, "size", styles.colorbar["title_font_size"], "colorbar", "title_font_size")
        if "title_font_family" in styles.colorbar:
            tf = cb.setdefault("title", {}).setdefault("font", {})
            _setdefault(tf, "family", styles.colorbar["title_font_family"], "colorbar", "title_font_family")
        if "title_font_color" in styles.colorbar:
            tf = cb.setdefault("title", {}).setdefault("font", {})
            _setdefault(tf, "color", styles.colorbar["title_font_color"], "colorbar", "title_font_color")
        if "tick_font_size" in styles.colorbar:
            tf = cb.setdefault("tickfont", {})
            _setdefault(tf, "size", styles.colorbar["tick_font_size"], "colorbar", "tick_font_size")
        if "tick_font_family" in styles.colorbar:
            tf = cb.setdefault("tickfont", {})
            _setdefault(tf, "family", styles.colorbar["tick_font_family"], "colorbar", "tick_font_family")
        if "tick_font_color" in styles.colorbar:
            tf = cb.setdefault("tickfont", {})
            _setdefault(tf, "color", styles.colorbar["tick_font_color"], "colorbar", "tick_font_color")
        if "bgcolor" in styles.colorbar:
            _setdefault(cb, "bgcolor", styles.colorbar["bgcolor"], "colorbar", "bgcolor")
        if "bordercolor" in styles.colorbar:
            _setdefault(cb, "bordercolor", styles.colorbar["bordercolor"], "colorbar", "bordercolor")
        if "borderwidth" in styles.colorbar:
            _setdefault(cb, "borderwidth", styles.colorbar["borderwidth"], "colorbar", "borderwidth")
        if "len" in styles.colorbar:
            _setdefault(cb, "len", styles.colorbar["len"], "colorbar", "len")
        if "thickness" in styles.colorbar:
            _setdefault(cb, "thickness", styles.colorbar["thickness"], "colorbar", "thickness")
        if "show" in styles.colorbar:
            _setdefault(trace, "showscale", styles.colorbar["show"], "colorbar", "show")

    # hoverlabel also lives on the trace
    if styles.hover:
        hl = trace.setdefault("hoverlabel", {})
        if "background_color" in styles.hover:
            _setdefault(hl, "bgcolor", styles.hover["background_color"], "hover", "background_color")
        if "border_color" in styles.hover:
            _setdefault(hl, "bordercolor", styles.hover["border_color"], "hover", "border_color")
        if "border_width" in styles.hover:
            _setdefault(hl, "borderwidth", styles.hover["border_width"], "hover", "border_width")
        if any(k in styles.hover for k in ("font_size", "font_family", "font_color")):
            hf = hl.setdefault("font", {})
            if "font_size" in styles.hover:
                _setdefault(hf, "size", styles.hover["font_size"], "hover", "font_size")
            if "font_family" in styles.hover:
                _setdefault(hf, "family", styles.hover["font_family"], "hover", "font_family")
            if "font_color" in styles.hover:
                _setdefault(hf, "color", styles.hover["font_color"], "hover", "font_color")


_register_builtin_themes()
