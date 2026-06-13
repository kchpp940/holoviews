from __future__ import annotations

import base64
from contextlib import contextmanager, suppress
from itertools import chain

import matplotlib as mpl
import numpy as np
import param
from matplotlib import pyplot as plt
from param.parameterized import bothmethod

from ...core import HoloMap
from ...core.options import Store
from ..artifact_manager import ArtifactKind, CleanupPolicy, artifact_manager
from ..renderer import HTML_TAGS, MIME_TYPES, Renderer
from .util import get_old_rcparams, get_tight_bbox

# <format name> : (animation writer, format,  anim_kwargs, extra_args)
ANIMATION_OPTS = {
    "webm": (
        "ffmpeg",
        "webm",
        {},
        ["-vcodec", "libvpx-vp9", "-b", "1000k", "-pix_fmt", "yuv420p"],
    ),
    "mp4": ("ffmpeg", "mp4", {"codec": "libx264"}, ["-pix_fmt", "yuv420p"]),
    "gif": ("pillow", "gif", {"fps": 10}, []),
    "scrubber": ("html", None, {"fps": 5}, None),
}


class _BboxCacheMirror(dict):
    """A dict subclass that mirrors reads/writes to the artifact_manager LRU cache.

    The authoritative store for MPL tight-bounding-box values is the
    artifact_manager LRU cache (keyed with ``("mpl_bbox", fig_id)``).
    This subclass exists purely for backwards compatibility with any
    code still using ``MPLRenderer.drawn[fig_id]`` directly — every
    operation is transparently synced.  This eliminates the dual-
    tracking (a.k.a. "double-entry bookkeeping") risk.
    """

    _CACHE_PREFIX = "mpl_bbox"

    def __getitem__(self, fig_id):
        key = (self._CACHE_PREFIX, fig_id)
        value = artifact_manager.cache_get(key, _SENTINEL)
        if value is _SENTINEL:
            raise KeyError(fig_id)
        return value

    def __setitem__(self, fig_id, value):
        key = (self._CACHE_PREFIX, fig_id)
        artifact_manager.cache_put(
            key,
            value,
            format="bbox",
            policy=CleanupPolicy.RENDER_CYCLE,
            refs={"fig_id": fig_id},
        )

    def __delitem__(self, fig_id):
        key = (self._CACHE_PREFIX, fig_id)
        if not artifact_manager.cache_has(key):
            raise KeyError(fig_id)
        # cache has no explicit delete; overwrite with None then evict by LRU
        artifact_manager.cache_put(key, None, format="bbox", policy=CleanupPolicy.SCOPE_EXIT)

    def __contains__(self, fig_id):
        return artifact_manager.cache_has((self._CACHE_PREFIX, fig_id))

    def get(self, fig_id, default=None):
        key = (self._CACHE_PREFIX, fig_id)
        value = artifact_manager.cache_get(key, _SENTINEL)
        return default if value is _SENTINEL else value

    def pop(self, fig_id, *args):
        key = (self._CACHE_PREFIX, fig_id)
        value = artifact_manager.cache_get(key, _SENTINEL)
        if value is _SENTINEL:
            if args:
                return args[0]
            raise KeyError(fig_id)
        # Remove by rewriting as short-lived; actual eviction happens via LRU
        artifact_manager.cache_put(key, None, format="bbox", policy=CleanupPolicy.SCOPE_EXIT)
        return value

    def clear(self):
        # Walk all CACHE_ENTRY artifacts and drop bbox ones
        for art in list(artifact_manager.list_artifacts(kind=ArtifactKind.CACHE_ENTRY)):
            if art.refs.get("cache_key", "").startswith("('mpl_bbox'"):
                art.release()

    def __len__(self):
        return sum(
            1
            for art in artifact_manager.list_artifacts(kind=ArtifactKind.CACHE_ENTRY, released=False)
            if art.refs.get("cache_key", "").startswith("('mpl_bbox'")
        )

    def __iter__(self):
        for art in artifact_manager.list_artifacts(kind=ArtifactKind.CACHE_ENTRY, released=False):
            ck = art.refs.get("cache_key", "")
            if ck.startswith("('mpl_bbox'"):
                try:
                    fig_id = int(ck.rsplit(",", 1)[-1].rstrip(")").strip())
                except (ValueError, IndexError):
                    continue
                yield fig_id

    def keys(self):
        return list(self)

    def values(self):
        return [self[k] for k in self]

    def items(self):
        return [(k, self[k]) for k in self]


_SENTINEL = object()


class MPLRenderer(Renderer):
    """Exporter used to render data from matplotlib, either to a stream
    or directly to file.

    The __call__ method renders an HoloViews component to raw data of
    a specified matplotlib format.  The save method is the
    corresponding method for saving a HoloViews objects to disk.

    The save_fig and save_anim methods are used to save matplotlib
    figure and animation objects. These match the two primary return
    types of plotting class implemented with matplotlib.

    """

    # NOTE: this used to be a plain dict that was written to in parallel
    # with the artifact_manager LRU cache, risking double-ownership and
    # stale references.  It is now a dict subclass that transparently
    # mirrors the artifact_manager cache (authoritative single source).
    # All reads and writes are forwarded; the legacy dict is no longer
    # an independent store.
    drawn = _BboxCacheMirror()

    backend = param.String("matplotlib", doc="The backend name.")

    dpi = param.Integer(
        default=72,
        doc="The render resolution in dpi (dots per inch)",
    )

    fig = param.Selector(
        default="auto",
        objects=["png", "svg", "pdf", "pgf", "html", None, "auto"],
        doc="""
        Output render format for static figures. If None, no figure
        rendering will occur. """,
    )

    holomap = param.Selector(
        default="auto",
        objects=["widgets", "scrubber", "webm", "mp4", "gif", None, "auto"],
        doc="""
        Output render multi-frame (typically animated) format. If
        None, no multi-frame rendering will occur.""",
    )

    interactive = param.Boolean(
        default=False,
        doc="""
        Whether to enable interactive plotting allowing interactive
        plotting with explicitly calling show.""",
    )

    mode = param.Selector(default="default", objects=["default"])

    mode_formats = {
        "fig": ["png", "svg", "pdf", "pgf", "html", None, "auto"],
        "holomap": ["widgets", "scrubber", "webm", "mp4", "gif", "html", None, "auto"],
    }

    counter = 0

    def show(self, obj):
        """Renders the supplied object and displays it using the active
        GUI backend.

        """
        if self.interactive:
            if isinstance(obj, list):
                return [self.get_plot(o) for o in obj]
            return self.get_plot(obj)

        from .plot import MPLPlot

        MPLPlot._close_figures = False
        try:
            plots = []
            objects = obj if isinstance(obj, list) else [obj]
            for o in objects:
                plots.append(self.get_plot(o))
            plt.show()
        except Exception:
            raise
        finally:
            MPLPlot._close_figures = True
        return plots[0] if len(plots) == 1 else plots

    @classmethod
    def plot_options(cls, obj, percent_size):
        """Given a holoviews object and a percentage size, apply heuristics
        to compute a suitable figure size. For instance, scaling layouts
        and grids linearly can result in unwieldy figure sizes when there
        are a large number of elements. As ad hoc heuristics are used,
        this functionality is kept separate from the plotting classes
        themselves.

        Used by the IPython Notebook display hooks and the save
        utility. Note that this can be overridden explicitly per object
        using the fig_size and size plot options.

        """
        from .plot import MPLPlot

        factor = percent_size / 100.0
        obj = obj.last if isinstance(obj, HoloMap) else obj
        options = Store.lookup_options(cls.backend, obj, "plot").options
        fig_size = options.get("fig_size", MPLPlot.fig_size) * factor

        return dict({"fig_size": fig_size}, **MPLPlot.lookup_options(obj, "plot").options)

    @bothmethod
    def get_size(self_or_cls, plot):
        w, h = plot.state.get_size_inches()
        dpi = self_or_cls.dpi if self_or_cls.dpi else plot.state.dpi
        return (int(w * dpi), int(h * dpi))

    def _figure_data(self, plot, fmt, bbox_inches="tight", as_script=False, **kwargs):
        """Render matplotlib figure object and return the corresponding
        data.  If as_script is True, the content will be split in an
        HTML and a JS component.

        Similar to IPython.core.pylabtools.print_figure but without
        any IPython dependency.

        """
        owner = type(self).__name__
        with artifact_manager.default_owner(owner):
            with artifact_manager.scope(f"mpl-figdata-{id(plot)}") as scope:
                artifact_manager.register(
                    ArtifactKind.MPL_FIGURE,
                    obj=plot.state,
                    policy=CleanupPolicy.RENDER_CYCLE,
                    refs={"plot_id": id(plot), "format": fmt},
                )

                if fmt in ["gif", "mp4", "webm"]:
                    with mpl.rc_context(rc=plot.fig_rcparams):
                        if bbox_inches == "tight":
                            self._adjust_figure_for_anim(plot, fmt)
                        anim = plot.anim(fps=self.fps)
                    data = self._anim_data(anim, fmt, scope=scope)
                else:
                    fig = plot.state

                    traverse_fn = lambda x: x.handles.get("bbox_extra_artists", None)
                    extra_artists = list(
                        chain.from_iterable(
                            artists for artists in plot.traverse(traverse_fn) if artists is not None
                        )
                    )

                    kw = dict(
                        format=fmt,
                        facecolor=fig.get_facecolor(),
                        edgecolor=fig.get_edgecolor(),
                        dpi=self.dpi,
                        bbox_inches=bbox_inches,
                        bbox_extra_artists=extra_artists,
                    )
                    kw.update(kwargs)

                    with np.errstate(invalid="ignore"):
                        with suppress(Exception):
                            kw = self._compute_bbox(fig, kw)
                        _, bytes_io = scope.create_bytesio(format=fmt)
                        fig.canvas.print_figure(bytes_io, **kw)
                    bytes_io.seek(0)
                    data = bytes_io.read()

                if as_script:
                    b64 = base64.b64encode(data).decode("utf-8")
                    (mime_type, tag) = MIME_TYPES[fmt], HTML_TAGS[fmt]
                    src = HTML_TAGS["base64"].format(mime_type=mime_type, b64=b64)
                    html = tag.format(src=src, mime_type=mime_type, css="")
                    scope.register_data(
                        html,
                        format="html",
                        policy=CleanupPolicy.SCOPE_EXIT,
                        refs={"source_fmt": fmt},
                    )
                    return html
                if fmt == "svg":
                    data = data.decode("utf-8")
                scope.register_data(
                    data,
                    format=fmt,
                    policy=CleanupPolicy.SCOPE_EXIT,
                )
                return data

    def _anim_data(self, anim, fmt, scope=None):
        """Render a matplotlib animation object and return the corresponding data."""
        (writer, _, anim_kwargs, extra_args) = ANIMATION_OPTS[fmt]
        if extra_args != []:
            anim_kwargs = dict(anim_kwargs, extra_args=extra_args)

        if self.fps is not None:
            anim_kwargs["fps"] = max([int(self.fps), 1])
        if self.dpi is not None:
            anim_kwargs["dpi"] = self.dpi
        if not hasattr(anim, "_encoded_video"):
            _manager = scope if scope is not None else artifact_manager
            _scope_owner = type(self).__name__
            with artifact_manager.default_owner(_scope_owner):
                if scope is None:
                    _ctx = artifact_manager.scope(f"mpl-anim-{id(anim)}")
                    _manager = _ctx.__enter__()
                else:
                    _ctx = None
                try:
                    art, _ = _manager.create_tempfile(
                        format=fmt,
                        policy=CleanupPolicy.SCOPE_EXIT,
                    )
                    anim.save(art.path, writer=writer, **anim_kwargs)
                    with open(art.path, "rb") as f:
                        video = f.read()
                finally:
                    if _ctx is not None:
                        _ctx.__exit__(None, None, None)
        return video

    def _compute_bbox(self, fig, kw):
        """Compute the tight bounding box for each figure once, reducing
        number of required canvas draw calls from N*2 to N+1 as a
        function of the number of frames.

        Tight bounding box computing code here mirrors:
        matplotlib.backend_bases.FigureCanvasBase.print_figure
        as it hasn't been factored out as a function.

        Single source of truth is the artifact_manager LRU cache.
        The legacy ``MPLRenderer.drawn`` dict is kept only as a
        read-through mirror (populated from the authoritative cache
        on demand) and should not be written to directly.
        """
        fig_id = id(fig)
        cache_key = ("mpl_bbox", fig_id)
        if kw["bbox_inches"] == "tight":
            cached = artifact_manager.cache_get(cache_key)
            if cached is None:
                fig.set_dpi(self.dpi)
                fig.canvas.draw()
                extra_artists = kw.pop("bbox_extra_artists", [])
                pad = mpl.rcParams["savefig.pad_inches"]
                bbox_inches = get_tight_bbox(fig, extra_artists, pad=pad)
                artifact_manager.cache_put(
                    cache_key,
                    bbox_inches,
                    format="bbox",
                    policy=CleanupPolicy.RENDER_CYCLE,
                    refs={"fig_id": fig_id},
                )
                kw["bbox_inches"] = bbox_inches
            else:
                kw["bbox_inches"] = cached
            # Clear any stale entry in the legacy mirror dict — authority
            # is now the artifact_manager LRU cache, so this reference
            # is not needed and risks memory leaks.
            MPLRenderer.drawn.pop(fig_id, None)
        return kw

    def _adjust_figure_for_anim(self, plot, fmt):
        """Adjust figure size and subplot positions to tightly fit all content.

        Matplotlib's animation writers do not support bbox_inches='tight',
        so animations can have clipped labels and titles. This method
        computes the tight bounding box of the rendered figure and adjusts
        the figure dimensions and axes positions so that all content fits
        within the figure bounds without clipping.
        """
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        fig = plot.state

        traverse_fn = lambda x: x.handles.get("bbox_extra_artists", None)
        extra_artists = list(
            chain.from_iterable(
                artists for artists in plot.traverse(traverse_fn) if artists is not None
            )
        )

        pad = mpl.rcParams["savefig.pad_inches"]

        # Ensure we have a non-interactive canvas for rendering, since
        # the figure may have been closed (plt.close) but still retain
        # a Tk/Qt canvas that errors on resize operations.
        if type(fig.canvas) is not FigureCanvasAgg:
            fig.canvas.manager = None
            FigureCanvasAgg(fig)

        dpi = self.dpi or fig.dpi
        fig.set_dpi(dpi)
        fig.canvas.draw()
        bbox_inches = get_tight_bbox(fig, extra_artists, pad=pad)

        orig_w, orig_h = fig.get_size_inches()
        new_w = bbox_inches.width
        new_h = bbox_inches.height

        # Video codecs like libx264 require even pixel dimensions.
        # Round up to the nearest even number of pixels for video formats.
        if fmt in ("mp4", "webm"):
            pw, ph = int(new_w * dpi), int(new_h * dpi)
            new_w = (pw + pw % 2) / dpi
            new_h = (ph + ph % 2) / dpi

        # Compute how to transform positions from old figure coordinates
        # to new figure coordinates. The tight bbox defines the visible
        # region in the old coordinate system; we need to map that region
        # to fill the new (resized) figure.
        x_shift = -bbox_inches.x0 / orig_w
        y_shift = -bbox_inches.y0 / orig_h
        x_scale = orig_w / new_w
        y_scale = orig_h / new_h

        for ax in fig.axes:
            pos = ax.get_position()
            new_pos = [
                (pos.x0 + x_shift) * x_scale,
                (pos.y0 + y_shift) * y_scale,
                pos.width * x_scale,
                pos.height * y_scale,
            ]
            ax.set_position(new_pos)

        # Reposition figure-level texts (e.g. suptitle) which use
        # figure-fraction coordinates and are not moved by axes adjustment.
        for text in fig.texts:
            x, y = text.get_position()
            text.set_position(((x + x_shift) * x_scale, (y + y_shift) * y_scale))

        fig.set_size_inches(new_w, new_h)

    @classmethod
    @contextmanager
    def state(cls):
        old_rcparams = get_old_rcparams()
        try:
            cls._rcParams = old_rcparams
            yield
        finally:
            mpl.rcParams.clear()
            mpl.rcParams.update(cls._rcParams)

    @classmethod
    def load_nb(cls, inline=True):
        """Initialize matplotlib backend"""
        import matplotlib.pyplot as plt

        backend = plt.get_backend()
        if backend not in ["agg", "module://ipykernel.pylab.backend_inline"]:
            plt.switch_backend("agg")
