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

def get_theme_styles_for_plot(obj, backend: _BACKEND_T) -> ThemeStyles:
    """Resolve the effective theme for a plot object and return its styles.

    Priority order (highest first):
      1. per-object theme (``.opts(theme=...)``)
      2. innermost ``with hv.opts.theme(...)`` context
      3. global default set via ``hv.opts.defaults_theme(...)``
    """
    from .options import _get_object_theme

    theme = _get_object_theme(obj) or get_active_theme()
    if theme is None:
        return ThemeStyles()
    raw = theme.get_styles(backend)
    return ThemeCapabilities.filter_styles(raw, backend)


# --- Bokeh -----------------------------------------------------------------

def apply_bokeh_theme_to_figure(plot, styles: ThemeStyles) -> None:
    """Apply *styles* to an already-created Bokeh ``Figure``.

    This is called by the backend immediately after the figure and
    its axes/toolbar have been constructed, so we can mutate model
    attributes directly instead of hoping they pass through the
    plot-option keyword filter.
    """
    if not styles:
        return

    # --- background ------------------------------------------------------
    if styles.background:
        if "color" in styles.background:
            plot.background_fill_color = styles.background["color"]
        if "border_color" in styles.background:
            plot.border_fill_color = styles.background["border_color"]

    # --- font / title ---------------------------------------------------
    if styles.font:
        if "family" in styles.font:
            plot.title.text_font = styles.font["family"]
        if "size" in styles.font:
            plot.title.text_font_size = styles.font["size"]
        if "style" in styles.font:
            plot.title.text_font_style = styles.font["style"]
        if "color" in styles.font:
            plot.title.text_color = styles.font["color"]

    # --- axes ------------------------------------------------------------
    if styles.font:
        for axis in list(plot.xaxis) + list(plot.yaxis):
            if "family" in styles.font:
                axis.axis_label_text_font = styles.font["family"]
                axis.major_label_text_font = styles.font["family"]
            if "size" in styles.font:
                axis.axis_label_text_font_size = styles.font["size"]
                axis.major_label_text_font_size = styles.font["size"]
            if "style" in styles.font:
                axis.axis_label_text_font_style = styles.font["style"]
            if "color" in styles.font:
                axis.axis_label_text_color = styles.font["color"]
                axis.major_label_text_color = styles.font["color"]

    # --- grid ------------------------------------------------------------
    if styles.grid:
        xgs, ygs = {}, {}
        if "show" in styles.grid and not styles.grid["show"]:
            plot.xgrid.grid_line_color = None
            plot.ygrid.grid_line_color = None
        else:
            if "color" in styles.grid:
                xgs["grid_line_color"] = styles.grid["color"]
                ygs["grid_line_color"] = styles.grid["color"]
            if "alpha" in styles.grid:
                xgs["grid_line_alpha"] = styles.grid["alpha"]
                ygs["grid_line_alpha"] = styles.grid["alpha"]
            if "line_width" in styles.grid:
                xgs["grid_line_width"] = styles.grid["line_width"]
                ygs["grid_line_width"] = styles.grid["line_width"]
            if "linestyle" in styles.grid:
                xgs["grid_line_dash"] = styles.grid["linestyle"]
                ygs["grid_line_dash"] = styles.grid["linestyle"]
        if xgs:
            for g in plot.xgrid:
                g.update(**xgs)
        if ygs:
            for g in plot.ygrid:
                g.update(**ygs)

    # --- toolbar ---------------------------------------------------------
    if styles.toolbar and plot.toolbar is not None:
        if "autohide" in styles.toolbar:
            plot.toolbar.autohide = styles.toolbar["autohide"]
        if "show" in styles.toolbar and not styles.toolbar["show"]:
            plot.toolbar_location = None


# --- Matplotlib -----------------------------------------------------------

def apply_matplotlib_theme_to_rcparams(styles: ThemeStyles) -> dict[str, t.Any]:
    """Return an ``rcParams``-style dictionary derived from *styles*."""
    rc: dict[str, t.Any] = {}

    if styles.font:
        if "family" in styles.font:
            rc["font.family"] = styles.font["family"]
        if "size" in styles.font:
            rc["font.size"] = styles.font["size"]
        if "weight" in styles.font:
            rc["font.weight"] = styles.font["weight"]

    if styles.background:
        if "color" in styles.background:
            rc["figure.facecolor"] = styles.background["color"]
            rc["axes.facecolor"] = styles.background["color"]
        if "edge_color" in styles.background:
            rc["axes.edgecolor"] = styles.background["edge_color"]

    if styles.grid:
        if "show" in styles.grid:
            rc["axes.grid"] = styles.grid["show"]
        if "color" in styles.grid:
            rc["grid.color"] = styles.grid["color"]
        if "alpha" in styles.grid:
            rc["grid.alpha"] = styles.grid["alpha"]
        if "line_width" in styles.grid:
            rc["grid.linewidth"] = styles.grid["line_width"]
        if "linestyle" in styles.grid:
            rc["grid.linestyle"] = styles.grid["linestyle"]

    if styles.legend:
        if "fontsize" in styles.legend:
            rc["legend.fontsize"] = styles.legend["fontsize"]
        if "title_fontsize" in styles.legend:
            rc["legend.title_fontsize"] = styles.legend["title_fontsize"]
        if "framealpha" in styles.legend:
            rc["legend.framealpha"] = styles.legend["framealpha"]
        if "edgecolor" in styles.legend:
            rc["legend.edgecolor"] = styles.legend["edgecolor"]
        if "facecolor" in styles.legend:
            rc["legend.facecolor"] = styles.legend["facecolor"]
        if "borderpad" in styles.legend:
            rc["legend.borderpad"] = styles.legend["borderpad"]
        if "labelspacing" in styles.legend:
            rc["legend.labelspacing"] = styles.legend["labelspacing"]
        if "frame" in styles.legend:
            rc["legend.frameon"] = styles.legend["frame"]

    if styles.toolbar:
        if "show" in styles.toolbar:
            rc["toolbar"] = "toolbar2" if styles.toolbar["show"] else "None"

    return rc


def apply_matplotlib_theme_to_axes(ax, styles: ThemeStyles) -> None:
    """Apply theme styles directly to a Matplotlib ``Axes``."""
    if not styles:
        return
    if styles.legend and "show" in styles.legend and not styles.legend["show"]:
        legend = ax.get_legend()
        if legend is not None:
            legend.remove()


# --- Plotly ----------------------------------------------------------------

def apply_plotly_theme_to_layout(
    layout: dict[str, t.Any],
    styles: ThemeStyles,
    xaxis: dict[str, t.Any] | None = None,
    yaxis: dict[str, t.Any] | None = None,
) -> None:
    """Merge theme *styles* into a Plotly ``layout`` dict in place.

    This is called by the Plotly backend before the layout is wrapped
    into a ``Figure``.  Unlike the option-keyword pipeline, here we
    write directly to the nested dict structure Plotly actually uses,
    so every declared capability reaches the rendered output.
    """
    if not styles:
        return

    # --- font ------------------------------------------------------------
    if styles.font:
        font = layout.setdefault("font", {})
        if "family" in styles.font:
            font["family"] = styles.font["family"]
        if "size" in styles.font:
            font["size"] = styles.font["size"]
        if "color" in styles.font:
            font["color"] = styles.font["color"]

    # --- background -----------------------------------------------------
    if styles.background:
        if "color" in styles.background:
            layout["paper_bgcolor"] = styles.background["color"]
            layout["plot_bgcolor"] = styles.background["color"]

    # --- grid / axes ----------------------------------------------------
    if styles.grid and xaxis is not None:
        if "show" in styles.grid:
            xaxis["showgrid"] = styles.grid["show"]
            if yaxis is not None:
                yaxis["showgrid"] = styles.grid["show"]
        if "color" in styles.grid:
            xaxis["gridcolor"] = styles.grid["color"]
            if yaxis is not None:
                yaxis["gridcolor"] = styles.grid["color"]
        if "width" in styles.grid:
            xaxis["gridwidth"] = styles.grid["width"]
            if yaxis is not None:
                yaxis["gridwidth"] = styles.grid["width"]

    # --- font on axes --------------------------------------------------
    if styles.font:
        if xaxis is not None:
            xf = xaxis.setdefault("titlefont", {})
            xtf = xaxis.setdefault("tickfont", {})
            if "family" in styles.font:
                xf["family"] = styles.font["family"]
                xtf["family"] = styles.font["family"]
            if "size" in styles.font:
                xf["size"] = styles.font["size"]
                xtf["size"] = styles.font["size"]
            if "color" in styles.font:
                xf["color"] = styles.font["color"]
                xtf["color"] = styles.font["color"]
        if yaxis is not None:
            yf = yaxis.setdefault("titlefont", {})
            ytf = yaxis.setdefault("tickfont", {})
            if "family" in styles.font:
                yf["family"] = styles.font["family"]
                ytf["family"] = styles.font["family"]
            if "size" in styles.font:
                yf["size"] = styles.font["size"]
                ytf["size"] = styles.font["size"]
            if "color" in styles.font:
                yf["color"] = styles.font["color"]
                ytf["color"] = styles.font["color"]

    # --- legend ---------------------------------------------------------
    if styles.legend:
        legend = layout.setdefault("legend", {})
        if "position" in styles.legend:
            pos = styles.legend["position"]
            if isinstance(pos, tuple):
                legend["x"] = pos[0]
                legend["y"] = pos[1]
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
                    legend["x"] = shortcut["x"]
                    legend["y"] = shortcut["y"]
        if "orientation" in styles.legend:
            legend["orientation"] = styles.legend["orientation"]
        if "show" in styles.legend:
            legend["visible"] = styles.legend["show"]
        if "bgcolor" in styles.legend:
            legend["bgcolor"] = styles.legend["bgcolor"]
        if "bordercolor" in styles.legend:
            legend["bordercolor"] = styles.legend["bordercolor"]
        if "borderwidth" in styles.legend:
            legend["borderwidth"] = styles.legend["borderwidth"]
        if any(k in styles.legend for k in ("font_size", "font_family", "font_color")):
            lf = legend.setdefault("font", {})
            if "font_size" in styles.legend:
                lf["size"] = styles.legend["font_size"]
            if "font_family" in styles.legend:
                lf["family"] = styles.legend["font_family"]
            if "font_color" in styles.legend:
                lf["color"] = styles.legend["font_color"]
        if any(k in styles.legend for k in ("title_font_size", "title_font_family", "title_font_color")):
            title = legend.setdefault("title", {})
            tf = title.setdefault("font", {})
            if "title_font_size" in styles.legend:
                tf["size"] = styles.legend["title_font_size"]
            if "title_font_family" in styles.legend:
                tf["family"] = styles.legend["title_font_family"]
            if "title_font_color" in styles.legend:
                tf["color"] = styles.legend["title_font_color"]

    # --- hover ---------------------------------------------------------
    if styles.hover:
        if "mode" in styles.hover:
            layout["hovermode"] = styles.hover["mode"]
        hl = {}
        if "background_color" in styles.hover:
            hl["bgcolor"] = styles.hover["background_color"]
        if "border_color" in styles.hover:
            hl["bordercolor"] = styles.hover["border_color"]
        if any(k in styles.hover for k in ("font_size", "font_family", "font_color")):
            hf = hl.setdefault("font", {})
            if "font_size" in styles.hover:
                hf["size"] = styles.hover["font_size"]
            if "font_family" in styles.hover:
                hf["family"] = styles.hover["font_family"]
            if "font_color" in styles.hover:
                hf["color"] = styles.hover["font_color"]
        if hl:
            layout["hoverlabel"] = hl


def apply_plotly_theme_to_trace(trace: dict[str, t.Any], styles: ThemeStyles) -> None:
    """Merge theme *styles* into a single Plotly trace dictionary."""
    if not styles:
        return

    # colorbar lives on the trace
    if styles.colorbar:
        cb = trace.setdefault("colorbar", {})
        if "title_font_size" in styles.colorbar:
            cb.setdefault("title", {}).setdefault("font", {})["size"] = styles.colorbar["title_font_size"]
        if "title_font_family" in styles.colorbar:
            cb.setdefault("title", {}).setdefault("font", {})["family"] = styles.colorbar["title_font_family"]
        if "title_font_color" in styles.colorbar:
            cb.setdefault("title", {}).setdefault("font", {})["color"] = styles.colorbar["title_font_color"]
        if "tick_font_size" in styles.colorbar:
            cb.setdefault("tickfont", {})["size"] = styles.colorbar["tick_font_size"]
        if "tick_font_family" in styles.colorbar:
            cb.setdefault("tickfont", {})["family"] = styles.colorbar["tick_font_family"]
        if "tick_font_color" in styles.colorbar:
            cb.setdefault("tickfont", {})["color"] = styles.colorbar["tick_font_color"]
        if "bgcolor" in styles.colorbar:
            cb["bgcolor"] = styles.colorbar["bgcolor"]
        if "bordercolor" in styles.colorbar:
            cb["bordercolor"] = styles.colorbar["bordercolor"]
        if "borderwidth" in styles.colorbar:
            cb["borderwidth"] = styles.colorbar["borderwidth"]
        if "len" in styles.colorbar:
            cb["len"] = styles.colorbar["len"]
        if "thickness" in styles.colorbar:
            cb["thickness"] = styles.colorbar["thickness"]
        if "show" in styles.colorbar:
            trace["showscale"] = styles.colorbar["show"]

    # hoverlabel also lives on the trace
    if styles.hover:
        hl = trace.setdefault("hoverlabel", {})
        if "background_color" in styles.hover:
            hl["bgcolor"] = styles.hover["background_color"]
        if "border_color" in styles.hover:
            hl["bordercolor"] = styles.hover["border_color"]
        if "border_width" in styles.hover:
            hl["borderwidth"] = styles.hover["border_width"]
        if any(k in styles.hover for k in ("font_size", "font_family", "font_color")):
            hf = hl.setdefault("font", {})
            if "font_size" in styles.hover:
                hf["size"] = styles.hover["font_size"]
            if "font_family" in styles.hover:
                hf["family"] = styles.hover["font_family"]
            if "font_color" in styles.hover:
                hf["color"] = styles.hover["font_color"]


_register_builtin_themes()
