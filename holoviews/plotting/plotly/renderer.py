from __future__ import annotations

import base64
from io import BytesIO

import panel as pn
import param
from param.parameterized import bothmethod

from ...core import HoloMap
from ...core.options import Store
from ..renderer import HTML_TAGS, MIME_TYPES, Renderer, SaveContext
from .callbacks import callbacks
from .util import (
    PLOTLY_GE_6_0_0,
    _convert_numpy_in_fig_dict,
    clean_internal_figure_properties,
)

with param.logging_level("CRITICAL"):
    import plotly.graph_objs as go


def _PlotlyHoloviewsPane(fig_dict, **kwargs):
    """Custom Plotly pane constructor for use by the HoloViews Pane."""
    # Remove internal HoloViews properties
    clean_internal_figure_properties(fig_dict)

    config = fig_dict.pop("config", {})
    if config.get("responsive"):
        kwargs["sizing_mode"] = "stretch_both"
    plotly_pane = pn.pane.Plotly(
        fig_dict, viewport_update_policy="mouseup", config=config, **kwargs
    )

    # Register callbacks on pane
    for callback_cls in callbacks.values():
        for callback_prop in callback_cls.callback_properties:
            plotly_pane.param.watch(
                lambda event, cls=callback_cls, prop=callback_prop: (
                    cls.update_streams_from_property_update(prop, event.new, event.obj.object)
                ),
                callback_prop,
            )
    return plotly_pane


class PlotlyRenderer(Renderer):
    backend = param.String(default="plotly", doc="The backend name.")

    fig = param.Selector(
        default="auto",
        objects=["html", "png", "svg", "auto"],
        doc="""
        Output render format for static figures. If None, no figure
        rendering will occur. """,
    )

    holomap = param.Selector(
        default="auto",
        objects=["scrubber", "widgets", "gif", None, "auto"],
        doc="""
        Output render multi-frame (typically animated) format. If
        None, no multi-frame rendering will occur.""",
    )

    mode_formats = {
        "fig": ["html", "png", "svg"],
        "holomap": ["widgets", "scrubber", "gif", "auto"],
    }

    widgets = ["scrubber", "widgets"]

    _loaded = False

    _render_with_panel = True

    @bothmethod
    def _collect_plotly_config(self_or_cls, obj, seen=None):
        """Recursively walk a HoloViews object tree and collect every
        Plotly ``config`` from leaf elements via ``get_plot_state``.

        Handles nested Layout, AdjointLayout, HoloMap frames, and
        DynamicMap so that widgets / animated views don't lose config.
        """
        if seen is None:
            seen = set()
        oid = id(obj)
        if oid in seen:
            return {}
        seen.add(oid)

        merged = {}

        try:
            from ...core import Layout, AdjointLayout, DynamicMap, HoloMap
            from ...core.element import Element

            if isinstance(obj, (Layout, AdjointLayout)):
                for child in obj:
                    child_cfg = self_or_cls._collect_plotly_config(child, seen)
                    merged.update(child_cfg)
            elif isinstance(obj, HoloMap):
                if len(obj) > 0:
                    sample = obj.last if obj.last is not None else list(obj.values())[0]
                    child_cfg = self_or_cls._collect_plotly_config(sample, seen)
                    merged.update(child_cfg)
            elif isinstance(obj, DynamicMap):
                try:
                    sample = obj[obj.dimensions[0].range[0]] if obj.dimensions else None
                    if sample is not None:
                        child_cfg = self_or_cls._collect_plotly_config(sample, seen)
                        merged.update(child_cfg)
                except Exception:
                    pass
            elif isinstance(obj, Element):
                try:
                    fig_dict = self_or_cls.get_plot_state(obj)
                    cfg = fig_dict.get("config", {})
                    if cfg:
                        merged.update(dict(cfg))
                except Exception:
                    pass

            try:
                fig_dict = self_or_cls.get_plot_state(obj)
                cfg = fig_dict.get("config", {})
                if cfg:
                    merged.update(dict(cfg))
            except Exception:
                pass
        except Exception:
            pass

        return merged

    @bothmethod
    def _save_from_context(self_or_cls, ctx: SaveContext):
        """Plotly-specific save consuming a normalized SaveContext.

        Config flow (unified, context-driven):
          1. ``_collect_plotly_config``  walks ctx.obj recursively and
             merges every figure's config into ctx.plotly_config.
          2. For **Viewable** (Panel widget) saves: temporarily wraps
             ``_PlotlyHoloviewsPane`` so that every lazily-created
             Plotly pane inherits the merged ctx.plotly_config.
          3. For **non-Viewable** (png/svg/gif) saves: merges
             ctx.plotly_config into the rendered figure dict before
             image encoding.
        """
        ctx.plotly_config = self_or_cls._collect_plotly_config(ctx.obj)

        self_or_cls._build_plot(ctx)

        if ctx.is_viewable:
            original_constructor = pn.pane.HoloViews._panes.get("plotly")

            def _wrapped_constructor(fig_dict, **kwargs):
                existing_cfg = dict(fig_dict.get("config", {}))
                existing_cfg.update(ctx.plotly_config)
                fig_dict["config"] = existing_cfg
                if original_constructor is not None:
                    return original_constructor(fig_dict, **kwargs)
                return pn.pane.Plotly(
                    fig_dict, viewport_update_policy="mouseup", config=existing_cfg, **kwargs
                )

            pn.pane.HoloViews._panes["plotly"] = _wrapped_constructor
            try:
                ctx.plot.layout.save(
                    ctx.target, embed=True, resources=ctx.resources, title=ctx.title
                )
            finally:
                if original_constructor is not None:
                    pn.pane.HoloViews._panes["plotly"] = original_constructor
            return

        rendered = self_or_cls(ctx.plot, ctx.fmt)
        if rendered is None:
            return
        (_data, info) = rendered

        if ctx.plotly_config and ctx.fmt in ("png", "svg", "gif"):
            try:
                fig_dict = self_or_cls.get_plot_state(ctx.plot)
                existing_cfg = dict(fig_dict.get("config", {}))
                existing_cfg.update(ctx.plotly_config)
                fig_dict["config"] = existing_cfg
                figure = go.Figure(fig_dict)
                import plotly.io as pio
                if ctx.fmt == "svg":
                    _data = pio.to_image(figure, ctx.fmt).decode("utf-8")
                else:
                    _data = pio.to_image(figure, ctx.fmt, validate=False)
                rendered = (_data, info)
            except Exception:
                pass

        encoded = self_or_cls.encode(rendered)
        prefix = self_or_cls._save_prefix(info["file-ext"])
        if prefix:
            encoded = prefix + encoded
        if ctx.file_ext is None:
            ctx.file_ext = info["file-ext"]
        self_or_cls._write_output(ctx, encoded)

    @bothmethod
    def get_plot_state(self_or_cls, obj, doc=None, renderer=None, numpy_convert=False, **kwargs):
        """Given a HoloViews Viewable return a corresponding figure dictionary.
        Allows cleaning the dictionary of any internal properties that were added

        """
        fig_dict = super().get_plot_state(obj, renderer, **kwargs)
        config = fig_dict.get("config", {})

        # Remove internal properties (e.g. '_id', '_dim')
        clean_internal_figure_properties(fig_dict)

        # Run through Figure constructor to normalize keys
        # (e.g. to expand magic underscore notation)
        fig_dict = go.Figure(fig_dict).to_dict()
        fig_dict["config"] = config

        # Remove template
        fig_dict.get("layout", {}).pop("template", None)

        if numpy_convert and PLOTLY_GE_6_0_0:
            return _convert_numpy_in_fig_dict(fig_dict)

        return fig_dict

    def _figure_data(self, plot, fmt, as_script=False, **kwargs):
        if fmt == "gif":
            import plotly.io as pio
            from PIL import Image
            from plotly.io.orca import ensure_server, shutdown_server, status

            running = status.state == "running"
            if not running:
                ensure_server()

            nframes = len(plot)
            frames = []
            for i in range(nframes):
                plot.update(i)
                img_bytes = BytesIO()
                figure = go.Figure(self.get_plot_state(plot))
                img = pio.to_image(figure, "png", validate=False)
                img_bytes.write(img)
                frames.append(Image.open(img_bytes))

            if not running:
                shutdown_server()

            bio = BytesIO()
            duration = (1.0 / self.fps) * 1000
            frames[0].save(
                bio,
                format="GIF",
                append_images=frames[1:],
                save_all=True,
                duration=duration,
                loop=0,
            )
            bio.seek(0)
            data = bio.read()
        elif fmt in ("png", "svg"):
            import plotly.io as pio

            # Wrapping plot.state in go.Figure here performs validation
            # and applies any default theme.
            figure = go.Figure(self.get_plot_state(plot))
            data = pio.to_image(figure, fmt)

            if fmt == "svg":
                data = data.decode("utf-8")
        else:
            raise ValueError(f"Unsupported format: {fmt}")

        if as_script:
            b64 = base64.b64encode(data).decode("utf-8")
            (mime_type, tag) = MIME_TYPES[fmt], HTML_TAGS[fmt]
            src = HTML_TAGS["base64"].format(mime_type=mime_type, b64=b64)
            div = tag.format(src=src, mime_type=mime_type, css="")
            return div
        return data

    @classmethod
    def plot_options(cls, obj, percent_size):
        factor = percent_size / 100.0
        obj = obj.last if isinstance(obj, HoloMap) else obj
        plot = Store.registry[cls.backend].get(type(obj), None)
        options = plot.lookup_options(obj, "plot").options
        width = options.get("width", plot.width) * factor
        height = options.get("height", plot.height) * factor
        return dict(options, width=int(width), height=int(height))

    @classmethod
    def load_nb(cls, inline=True):
        """Loads the plotly notebook resources."""
        import panel.models.plotly  # noqa: F401

        cls._loaded = True
        if "plotly" not in getattr(pn.extension, "_loaded_extensions", ["plotly"]):
            pn.extension._loaded_extensions.append("plotly")


def _activate_plotly_backend(renderer):
    if renderer == "plotly":
        pn.pane.HoloViews._panes["plotly"] = _PlotlyHoloviewsPane


Store._backend_switch_hooks.append(_activate_plotly_backend)
