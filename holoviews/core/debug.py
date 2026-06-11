"""Debug context for DynamicMap and datashader/rasterize operations.

Provides a unified mechanism to collect and access debugging information
across streams, operations, renderers, and backend plots.

Key design:
- Each DynamicMap / Plot can have its own bound DebugContext via a
  ``debug_context`` attribute.
- A thread-local ``contextvars.ContextVar`` tracks the *active* context
  during a render cycle, so operations (rasterize/datashade) and helpers
  can record information into the *correct* per-instance context
  without depending on the global ``hv.debug`` container.
- Frames carry an ``owner_id`` / ``owner_type`` so a single context can
  serve multiple owners and still be filtered later.
- Contexts support optional ``parent`` linking for aggregation.
"""

from __future__ import annotations

import contextvars
import threading
import time
import typing as t
import uuid
from collections import defaultdict
from contextlib import contextmanager

import param

if t.TYPE_CHECKING:
    from collections.abc import Iterator


# ---------------------------------------------------------------------------
# ContextVar – tracks the currently-active DebugContext during a render
# ---------------------------------------------------------------------------

_active_debug_context: contextvars.ContextVar["DebugContext | None"] = contextvars.ContextVar(
    "holoviews_active_debug_context", default=None
)

_active_frame_owner: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "holoviews_active_frame_owner", default=None
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _short_id() -> str:
    """Generate a short, human-friendly id string."""
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# DebugContext
# ---------------------------------------------------------------------------


class DebugContext(param.Parameterized):
    """Unified, bindable debug context for collecting debugging information.

    A :class:`DebugContext` can be:
    * used as a **global singleton** (``hv.debug``) for convenience
    * **bound to a specific DynamicMap / Plot instance** via the
      ``debug_context`` attribute so information from that instance is
      kept separate and identifiable (``owner_id`` / ``owner_type``)
    * **linked to a parent** via the ``parent`` parameter so per-instance
      frames are also forwarded to an aggregating context (e.g. the global one)

    Information categories recorded per frame:
    - ``streams``: stream parameter values + triggering information
    - ``cache``: cache hit/miss information
    - ``operation``: range clipping, sampling resolution, aggregation dims
    - ``render``: actual rendering ranges from the backend
    - ``timing``: timing information for each processing stage
    - ``redraw_reason``: textual description of why a redraw happened

    Each frame also carries metadata for correlation:
    - ``frame_id``: unique id of the frame
    - ``owner_id``: id of the DynamicMap/Plot that "owns" the frame
    - ``owner_type``: type name of the owner
    - ``stream_event_id``: id of the stream event (if any) that triggered it
    - ``renderer_id``: id of the renderer that produced the frame
    """

    enabled = param.Boolean(
        default=False,
        doc="""
        Whether debugging information collection is enabled.
        When disabled, all record calls are no-ops for minimal overhead.""",
    )

    max_frames = param.Integer(
        default=50,
        bounds=(1, 10000),
        doc="""
        Maximum number of frames to retain in this context.
        Older frames are automatically evicted (FIFO).""",
    )

    propagate_to_parent = param.Boolean(
        default=True,
        doc="""
        Whether frames recorded in this context should also be forwarded
        to the parent context (if one is set).""",
    )

    parent = param.ClassSelector(
        class_=param.Parameterized,  # DebugContext, declared below to avoid forward-ref issues
        allow_None=True,
        default=None,
        doc="""
        Optional parent DebugContext. Frames recorded in this context
        may optionally be forwarded to the parent for aggregation.""",
    )

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, **params):
        super().__init__(**params)
        # Ensure parent type is really a DebugContext (avoids forward-ref loop)
        if self.parent is not None and not isinstance(self.parent, DebugContext):
            raise TypeError("parent must be a DebugContext or None")

        self._frames: list[dict] = []
        self._lock = threading.RLock()  # reentrant: recording may recurse via parent
        self._frame_counter = 0

        # Thread-local stack for nested .frame() / .as_active() calls.
        # Each thread gets its own stack so the contextvar restoration is
        # thread-safe even though ContextVar already handles concurrency.
        self._tls = threading.local()

    # ------------------------------------------------------------------
    # Activation – push/pop this context on the ContextVar stack
    # ------------------------------------------------------------------

    @contextmanager
    def as_active(self, owner_id: str | None = None, owner_type: str | None = None) -> Iterator[None]:
        """Temporarily make this context the "active" one.

        Operations like ``rasterize`` / ``datashade`` read the active
        context via :func:`get_active_context` so they can record into
        the correct per-instance context without explicit plumbing.

        Optionally also sets the *active frame owner* (an ``owner_id``,
        ``owner_type`` pair) which every record call will attach to the
        current frame automatically.
        """
        # If not enabled we still push a token so the exit path is clean,
        # but nothing gets recorded anyway.
        ctx_token = _active_debug_context.set(self)
        owner_token = None
        if owner_id and owner_type:
            owner_token = _active_frame_owner.set((owner_id, owner_type))
        try:
            yield
        finally:
            _active_debug_context.reset(ctx_token)
            if owner_token is not None:
                _active_frame_owner.reset(owner_token)

    # ------------------------------------------------------------------
    # Frame management
    # ------------------------------------------------------------------

    @contextmanager
    def frame(
        self,
        frame_id: str | None = None,
        *,
        owner_id: str | None = None,
        owner_type: str | None = None,
        stream_event_id: str | None = None,
        renderer_id: str | None = None,
    ) -> Iterator[dict]:
        """Context manager that creates, activates, and commits a frame.

        Parameters
        ----------
        frame_id : str, optional
            Explicit id. Auto-generated (short uuid) if not provided.
        owner_id : str, optional
            Id of the DynamicMap/Plot instance that owns this frame.
            If omitted, the value from the current active-frame-owner
            contextvar is used (set by :meth:`as_active`).
        owner_type : str, optional
            Type name of the owner (e.g. ``"DynamicMap"``).
        stream_event_id : str, optional
            Id of the stream event that triggered this frame.
        renderer_id : str, optional
            Id of the renderer producing this frame.

        Yields
        ------
        dict
            The (initially empty) frame information dictionary.
        """
        if not self.enabled:
            yield {}
            return

        # Resolve owner from contextvar fallback
        if (owner_id is None or owner_type is None):
            active_owner = _active_frame_owner.get()
            if active_owner is not None:
                if owner_id is None:
                    owner_id = active_owner[0]
                if owner_type is None:
                    owner_type = active_owner[1]

        # Generate ids
        if frame_id is None:
            frame_id = f"frm_{_short_id()}"
        self._frame_counter += 1

        frame_info: dict = {
            "frame_id": frame_id,
            "frame_seq": self._frame_counter,
            "timestamp": time.time(),
            # Owner identity – for filtering / per-instance inspection
            "owner_id": owner_id,
            "owner_type": owner_type,
            # Correlation ids
            "stream_event_id": stream_event_id,
            "renderer_id": renderer_id,
            # Per-frame data categories
            "streams": {"parameters": {}, "triggered": [], "changes": {}},
            "cache": {"history": [], "size": None, "last_miss_reason": None},
            "operation": {"operations": []},
            "render": {},
            "timing": {},
            "redraw_reason": None,
        }

        # Activate this context during the frame so record_* calls find it
        ctx_token = _active_debug_context.set(self)
        start_time = time.time()
        committed = False

        try:
            yield frame_info
            frame_info["timing"]["total"] = time.time() - start_time
            self._commit_frame(frame_info)
            committed = True
        finally:
            _active_debug_context.reset(ctx_token)
            if not committed:
                # Even on exception, record the (partial) frame with error marker
                frame_info["timing"]["total"] = time.time() - start_time
                frame_info.setdefault("timing", {})["error"] = True
                self._commit_frame(frame_info)

    def _commit_frame(self, frame_info: dict) -> None:
        """Append a frame to our storage (and optionally to the parent)."""
        with self._lock:
            self._frames.append(frame_info)
            # FIFO eviction
            while len(self._frames) > self.max_frames:
                self._frames.pop(0)
        if self.propagate_to_parent and self.parent is not None:
            # Copy to parent but mark the source. Parent keeps its own lock.
            parent_frame = dict(frame_info)
            parent_frame["source_context"] = self.name or id(self)
            self.parent._commit_frame(parent_frame)

    # ------------------------------------------------------------------
    # Convenience: obtain a frame (creates one lazily if none open)
    # ------------------------------------------------------------------

    def _ensure_frame(self) -> dict | None:
        """Return the currently open frame, or create a temporary one.

        Used by ``record_*`` helpers so that ad-hoc record calls outside
        an explicit ``frame()`` still work.
        """
        if not self.enabled:
            return None

        # Is a frame already open via contextvar chain?
        active_ctx = _active_debug_context.get()
        if active_ctx is self:
            # Walk frames to find one without "finalized" marker...
            # For simplicity we just keep a "last open frame" reference.
            last = self._frames[-1] if self._frames else None
            if last is not None and last.get("_open"):
                return last

        # Create a new (lazy) frame and immediately store it as open
        active_owner = _active_frame_owner.get()
        owner_id = active_owner[0] if active_owner else None
        owner_type = active_owner[1] if active_owner else None

        frame_id = f"frm_{_short_id()}"
        self._frame_counter += 1
        frame_info: dict = {
            "frame_id": frame_id,
            "frame_seq": self._frame_counter,
            "timestamp": time.time(),
            "owner_id": owner_id,
            "owner_type": owner_type,
            "stream_event_id": None,
            "renderer_id": None,
            "streams": {"parameters": {}, "triggered": [], "changes": {}},
            "cache": {"history": [], "size": None, "last_miss_reason": None},
            "operation": {"operations": []},
            "render": {},
            "timing": {},
            "redraw_reason": None,
            "_open": True,  # marks as lazily-created; will be finalized soon
        }
        with self._lock:
            self._frames.append(frame_info)
            while len(self._frames) > self.max_frames:
                self._frames.pop(0)

        if self.propagate_to_parent and self.parent is not None:
            # Do NOT propagate lazy frames – they would duplicate.
            # They'll propagate when finalized/committed properly.
            pass
        return frame_info

    def finalize_open_frames(self) -> None:
        """Finalize any lazily-created "open" frames (set total timing).

        This is automatically handled when the ``frame()`` context-manager
        is used. It is only needed when record_* calls happen outside a
        frame block and you want those frames to have a correct total time.
        """
        with self._lock:
            for f in self._frames:
                if f.get("_open"):
                    f["timing"]["total"] = time.time() - f["timestamp"]
                    del f["_open"]

    # ------------------------------------------------------------------
    # Recording helpers – every record_* call now works through the
    # "active" frame (from contextvar / lazy-create path above).
    # ------------------------------------------------------------------

    def record_streams(
        self,
        stream_info: dict,
        *,
        event_id: str | None = None,
        owner_id: str | None = None,
        owner_type: str | None = None,
    ) -> None:
        """Record stream parameter information.

        Parameters
        ----------
        stream_info : dict
            Keys may include ``parameters``, ``triggered``, ``changes``.
        event_id : str, optional
            Id to correlate this stream event with a frame.
        owner_id / owner_type : str, optional
            Explicit owner override (otherwise taken from active frame).
        """
        if not self.enabled:
            return
        frame = self._ensure_frame()
        if frame is None:
            return
        if owner_id is not None:
            frame["owner_id"] = owner_id
        if owner_type is not None:
            frame["owner_type"] = owner_type
        if event_id is not None:
            frame["stream_event_id"] = event_id

        streams = frame["streams"]
        if "parameters" in stream_info:
            streams["parameters"].update(stream_info["parameters"])
        if "triggered" in stream_info:
            triggered = list(streams.get("triggered", []))
            for t in stream_info["triggered"]:
                if t not in triggered:
                    triggered.append(t)
            streams["triggered"] = triggered
        if "changes" in stream_info:
            streams["changes"].update(stream_info["changes"])

    def record_cache(
        self,
        key: t.Any,
        hit: bool,
        cache_size: int | None = None,
        reason: str | None = None,
        *,
        owner_id: str | None = None,
        owner_type: str | None = None,
    ) -> None:
        """Record cache hit/miss information."""
        if not self.enabled:
            return
        frame = self._ensure_frame()
        if frame is None:
            return
        if owner_id is not None:
            frame["owner_id"] = owner_id
        if owner_type is not None:
            frame["owner_type"] = owner_type

        cache_info = frame["cache"]
        cache_info.setdefault("history", []).append(
            {
                "key": key,
                "hit": hit,
                "reason": reason,
                "timestamp": time.time(),
            }
        )
        if cache_size is not None:
            cache_info["size"] = cache_size
        if not hit:
            cache_info["last_miss_reason"] = reason

    def record_operation(
        self,
        op_name: str,
        op_info: dict,
        *,
        op_id: str | None = None,
        owner_id: str | None = None,
        owner_type: str | None = None,
    ) -> str:
        """Record operation information.

        Returns
        -------
        str
            The ``op_id`` assigned to this operation (for later correlation).
        """
        if not self.enabled:
            return op_id or ""
        frame = self._ensure_frame()
        if frame is None:
            return op_id or ""
        if owner_id is not None:
            frame["owner_id"] = owner_id
        if owner_type is not None:
            frame["owner_type"] = owner_type
        if op_id is None:
            op_id = f"op_{_short_id()}"

        ops = frame["operation"].setdefault("operations", [])
        op_entry = {
            "op_id": op_id,
            "name": op_name,
            "timestamp": time.time(),
            **op_info,
        }
        ops.append(op_entry)
        return op_id

    def record_render(
        self,
        backend: str,
        render_info: dict,
        *,
        renderer_id: str | None = None,
        owner_id: str | None = None,
        owner_type: str | None = None,
    ) -> None:
        """Record rendering information from the backend."""
        if not self.enabled:
            return
        frame = self._ensure_frame()
        if frame is None:
            return
        if owner_id is not None:
            frame["owner_id"] = owner_id
        if owner_type is not None:
            frame["owner_type"] = owner_type
        if renderer_id is not None:
            frame["renderer_id"] = renderer_id

        frame["render"][backend] = {
            "timestamp": time.time(),
            **render_info,
        }

    def record_redraw_reason(
        self,
        reason: str,
        *,
        owner_id: str | None = None,
        owner_type: str | None = None,
    ) -> None:
        """Record the reason for triggering a redraw."""
        if not self.enabled:
            return
        frame = self._ensure_frame()
        if frame is None:
            return
        if owner_id is not None:
            frame["owner_id"] = owner_id
        if owner_type is not None:
            frame["owner_type"] = owner_type

        existing = frame.get("redraw_reason")
        if existing and reason not in existing:
            frame["redraw_reason"] = f"{existing}; {reason}"
        else:
            frame["redraw_reason"] = reason

    def record_timing(
        self,
        stage: str,
        duration: float,
        *,
        owner_id: str | None = None,
        owner_type: str | None = None,
    ) -> None:
        """Record timing information for a processing stage."""
        if not self.enabled:
            return
        frame = self._ensure_frame()
        if frame is None:
            return
        if owner_id is not None:
            frame["owner_id"] = owner_id
        if owner_type is not None:
            frame["owner_type"] = owner_type

        frame["timing"][stage] = duration

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_frames(
        self,
        n: int | None = None,
        *,
        owner_id: str | None = None,
        owner_type: str | None = None,
    ) -> list[dict]:
        """Get collected frames, optionally filtered by owner.

        Parameters
        ----------
        n : int, optional
            Number of most recent frames to return (all if omitted).
        owner_id / owner_type : str, optional
            Filter frames belonging to a specific owner.

        Returns
        -------
        list[dict]
            Frames in chronological order (oldest → newest).
        """
        with self._lock:
            frames = list(self._frames)

        if owner_id is not None:
            frames = [f for f in frames if f.get("owner_id") == owner_id]
        if owner_type is not None:
            frames = [f for f in frames if f.get("owner_type") == owner_type]

        if n is not None:
            return frames[-n:]
        return frames

    def get_latest_frame(
        self,
        *,
        owner_id: str | None = None,
        owner_type: str | None = None,
    ) -> dict | None:
        """Get the most recent frame, optionally filtered by owner."""
        frames = self.get_frames(owner_id=owner_id, owner_type=owner_type)
        return frames[-1] if frames else None

    def get_owners(self) -> list[dict]:
        """Return the set of distinct (owner_id, owner_type) pairs seen so far."""
        with self._lock:
            pairs: dict[tuple, dict] = {}
            for f in self._frames:
                oid = f.get("owner_id")
                otype = f.get("owner_type")
                if oid is None:
                    continue
                key = (oid, otype)
                if key not in pairs:
                    pairs[key] = {
                        "owner_id": oid,
                        "owner_type": otype,
                        "frame_count": 0,
                        "first_seen": f["timestamp"],
                        "last_seen": f["timestamp"],
                    }
                info = pairs[key]
                info["frame_count"] += 1
                info["last_seen"] = f["timestamp"]
        return list(pairs.values())

    def clear(self, *, owner_id: str | None = None) -> None:
        """Clear collected debug information.

        Parameters
        ----------
        owner_id : str, optional
            If given, only clear frames belonging to this owner;
            otherwise clear everything.
        """
        with self._lock:
            if owner_id is None:
                self._frames.clear()
            else:
                self._frames = [
                    f for f in self._frames if f.get("owner_id") != owner_id
                ]

    # ------------------------------------------------------------------
    # Display – summary (text) / _repr_html_ (notebook)
    # ------------------------------------------------------------------

    def summary(self, n: int = 1, *, owner_id: str | None = None, owner_type: str | None = None) -> str:
        """Generate a human-readable summary of debug information."""
        if not self.enabled:
            return "DebugContext is disabled. Set enabled=True to enable."

        frames = self.get_frames(n, owner_id=owner_id, owner_type=owner_type)
        if not frames:
            return "No debug information collected yet."

        lines = ["=" * 72, "HoloViews DebugContext Summary", "=" * 72, ""]

        owners = self.get_owners()
        if owners:
            lines.append(f"Registered owners ({len(owners)}):")
            for o in owners:
                lines.append(
                    f"  - {o['owner_type']} id={o['owner_id'][:8]}…  "
                    f"frames={o['frame_count']}"
                )
            lines.append("")

        for i, frame in enumerate(reversed(frames)):
            idx = len(frames) - i
            owner = (
                f"{frame.get('owner_type', '?')}#{str(frame.get('owner_id', '?'))[:8]}"
            )
            lines.append(
                f"Frame {idx}: {frame['frame_id']}  "
                f"(owner={owner}  seq={frame.get('frame_seq', '?')})"
            )
            lines.append(f"  Timestamp : {time.ctime(frame['timestamp'])}")
            lines.append(f"  Total time: {frame['timing'].get('total', 'N/A'):.4f}s")
            if frame.get("stream_event_id"):
                lines.append(f"  Stream evt: {frame['stream_event_id']}")
            if frame.get("renderer_id"):
                lines.append(f"  Renderer  : {frame['renderer_id']}")
            if frame.get("redraw_reason"):
                lines.append(f"  Redraw    : {frame['redraw_reason']}")

            streams = frame.get("streams", {})
            if streams.get("parameters"):
                lines.append("  Streams:")
                for sname, sinfo in streams["parameters"].items():
                    lines.append(f"    {sname}: {sinfo}")
                if streams.get("triggered"):
                    lines.append(f"    Triggered: {streams['triggered']}")

            cache = frame.get("cache", {})
            history = cache.get("history", [])
            if history:
                lines.append("  Cache:")
                last = history[-1]
                lines.append(
                    f"    Last: {'HIT' if last['hit'] else 'MISS'}  key={last['key']}"
                )
                if not last["hit"] and last.get("reason"):
                    lines.append(f"      Reason: {last['reason']}")
                if cache.get("size") is not None:
                    lines.append(f"    Size: {cache['size']}")

            ops = frame.get("operation", {}).get("operations", [])
            if ops:
                lines.append("  Operations:")
                for op in ops:
                    lines.append(f"    {op.get('op_id','?')} {op.get('name','?')}:")
                    for k, v in op.items():
                        if k in {"op_id", "name", "timestamp"}:
                            continue
                        lines.append(f"      {k}: {v}")

            render = frame.get("render", {})
            if render:
                lines.append("  Render:")
                for backend, rinfo in render.items():
                    details = []
                    if "actual_range" in rinfo:
                        details.append(f"range={rinfo['actual_range']}")
                    if "plot_size" in rinfo:
                        details.append(f"size={rinfo['plot_size']}")
                    details_str = ", ".join(details)
                    lines.append(f"    {backend}: {details_str}")

            timing = {k: v for k, v in frame.get("timing", {}).items() if k != "total"}
            if timing:
                lines.append("  Timing:")
                for stage, duration in timing.items():
                    lines.append(f"    {stage}: {duration:.4f}s")

            lines.append("")

        return "\n".join(lines)

    def _repr_html_(
        self,
        *,
        owner_id: str | None = None,
        owner_type: str | None = None,
        title: str | None = None,
    ) -> str:
        """HTML representation for Jupyter notebooks."""
        if not self.enabled:
            return (
                "<div style='padding: 12px; background: #fff3cd; "
                "border: 1px solid #ffeeba; border-radius: 6px;'>"
                "<strong>DebugContext</strong>: Disabled. "
                "Set <code>debug_context.enabled=True</code> to enable."
                "</div>"
            )

        frames = self.get_frames(5, owner_id=owner_id, owner_type=owner_type)
        if not frames:
            return (
                "<div style='padding: 12px; background: #d1ecf1; "
                "border: 1px solid #bee5eb; border-radius: 6px;'>"
                "<strong>DebugContext</strong>: No debug information collected yet."
                "</div>"
            )

        title_str = title or "HoloViews DebugContext"
        if owner_id:
            title_str += f" (owner {str(owner_id)[:8]}…)"

        html = [
            "<div style='font-family: ui-monospace, SFMono-Regular, Menlo, monospace; "
            "font-size: 12px; max-height: 540px; overflow-y: auto; "
            "border: 1px solid #dee2e6; border-radius: 6px;'>",
            f"<div style='padding: 10px; background: #f1f3f5; "
            f"border-bottom: 1px solid #dee2e6; "
            f"font-weight: 600; color: #212529;'>{title_str}</div>",
        ]

        for i, frame in enumerate(reversed(frames)):
            frame_num = len(frames) - i
            bg = "#f8f9fa" if i % 2 == 0 else "#ffffff"
            owner_tag = ""
            if frame.get("owner_id"):
                owner_tag = (
                    f" <span style='background: #e7f5ff; color: #1971c2; "
                    f"padding: 1px 6px; border-radius: 3px; "
                    f"font-size: 11px;'>"
                    f"{frame.get('owner_type', '?')}"
                    f"#{str(frame['owner_id'])[:8]}</span>"
                )
            html.append(
                f"<div style='padding: 10px; margin: 8px; "
                f"background: {bg}; border: 1px solid #dee2e6; "
                f"border-radius: 5px;'>"
            )
            html.append(
                f"<div style='font-weight: 600; color: #007bff; "
                f"margin-bottom: 4px;'>"
                f"Frame {frame_num}: {frame['frame_id']}{owner_tag}</div>"
            )
            meta_parts = [
                time.ctime(frame["timestamp"]),
                f"total: {frame['timing'].get('total', 'N/A'):.4f}s",
            ]
            if frame.get("stream_event_id"):
                meta_parts.append(f"stream: {frame['stream_event_id'][:8]}")
            if frame.get("renderer_id"):
                meta_parts.append(f"renderer: {frame['renderer_id'][:8]}")
            html.append(
                f"<div style='color: #6c757d; font-size: 11px;'>"
                f"{' | '.join(meta_parts)}</div>"
            )

            if frame.get("redraw_reason"):
                html.append(
                    f"<div style='margin-top: 6px; padding: 4px 6px; "
                    f"background: #fff9db; border-left: 3px solid #fcc419; "
                    f"border-radius: 2px;'>"
                    f"<span style='color: #e67700; font-weight: 600;'>Redraw:</span> "
                    f"{frame['redraw_reason']}</div>"
                )

            streams = frame.get("streams", {})
            if streams.get("parameters"):
                html.append("<div style='margin-top: 6px;'><strong>Streams</strong></div>")
                html.append("<ul style='margin: 2px 0 0 18px; padding: 0;'>")
                for sname, sinfo in streams["parameters"].items():
                    html.append(f"<li><code>{sname}</code>: {sinfo}</li>")
                if streams.get("triggered"):
                    html.append(
                        f"<li style='color: #dc3545;'>"
                        f"Triggered: {streams['triggered']}</li>"
                    )
                html.append("</ul>")

            cache = frame.get("cache", {})
            history = cache.get("history", [])
            if history:
                html.append("<div style='margin-top: 6px;'><strong>Cache</strong></div>")
                html.append("<ul style='margin: 2px 0 0 18px; padding: 0;'>")
                for entry in history[-3:]:
                    status = "✓ HIT" if entry["hit"] else "✗ MISS"
                    color = "#28a745" if entry["hit"] else "#dc3545"
                    reason = f" ({entry['reason']})" if entry.get("reason") else ""
                    html.append(
                        f"<li><span style='color: {color}; font-weight: 600;'>"
                        f"{status}</span> key: <code>{entry['key']}</code>{reason}</li>"
                    )
                if cache.get("size") is not None:
                    html.append(f"<li>Cache size: {cache['size']}</li>")
                html.append("</ul>")

            ops = frame.get("operation", {}).get("operations", [])
            if ops:
                html.append("<div style='margin-top: 6px;'><strong>Operations</strong></div>")
                for op in ops:
                    op_id = op.get("op_id", "?")[:8]
                    html.append(
                        f"<div style='margin-left: 10px; margin-top: 3px; "
                        f"padding: 5px 7px; background: #e9ecef; "
                        f"border-radius: 3px;'>"
                        f"<div><code>{op.get('name', '?')}</code> "
                        f"<span style='font-size: 10px; color: #868e96;'>"
                        f"id={op_id}</span></div>"
                    )
                    details = []
                    if "input_range" in op:
                        details.append(f"Input: {op['input_range']}")
                    if "clipped_range" in op:
                        details.append(f"Clipped: {op['clipped_range']}")
                    if "sampling_resolution" in op and any(op["sampling_resolution"]):
                        details.append(f"Res: {op['sampling_resolution']}")
                    if "aggregation_size" in op:
                        details.append(f"Size: {op['aggregation_size']}")
                    if "aggregator" in op:
                        details.append(f"Agg: {op['aggregator']}")
                    if "data_points" in op:
                        details.append(f"Data: {op['data_points']}")
                    if details:
                        html.append(
                            f"<div style='font-size: 11px; color: #495057; "
                            f"margin-top: 2px;'>{' | '.join(details)}</div>"
                        )
                    html.append("</div>")

            render = frame.get("render", {})
            if render:
                html.append("<div style='margin-top: 6px;'><strong>Render</strong></div>")
                html.append("<ul style='margin: 2px 0 0 18px; padding: 0;'>")
                for backend, rinfo in render.items():
                    details = []
                    if "actual_range" in rinfo:
                        details.append(f"range={rinfo['actual_range']}")
                    if "plot_size" in rinfo:
                        details.append(f"size={rinfo['plot_size']}")
                    if "plot_type" in rinfo:
                        details.append(f"type={rinfo['plot_type']}")
                    html.append(f"<li><strong>{backend}</strong>: {' | '.join(details)}</li>")
                html.append("</ul>")

            timing = {k: v for k, v in frame.get("timing", {}).items() if k != "total"}
            if timing:
                html.append("<div style='margin-top: 6px;'><strong>Timing</strong></div>")
                html.append("<ul style='margin: 2px 0 0 18px; padding: 0;'>")
                for stage, duration in timing.items():
                    html.append(f"<li>{stage}: {duration:.4f}s</li>")
                html.append("</ul>")

            html.append("</div>")

        html.append("</div>")
        return "".join(html)

    def __repr__(self) -> str:
        state = "enabled" if self.enabled else "disabled"
        with self._lock:
            n_frames = len(self._frames)
            n_owners = len({f.get("owner_id") for f in self._frames if f.get("owner_id")})
        return (
            f"<DebugContext name={self.name!r} {state} "
            f"frames={n_frames} owners={n_owners}>"
        )


# Fix the parent type hint loop (class_ is already validated in __init__)
DebugContext.param["parent"].class_ = DebugContext


# ---------------------------------------------------------------------------
# Global singleton context – kept as default aggregator
# ---------------------------------------------------------------------------

debug = DebugContext(name="holoviews_global_debug")


# ---------------------------------------------------------------------------
# Module-level helpers – independent of any specific instance
# ---------------------------------------------------------------------------


def get_active_context() -> DebugContext | None:
    """Return the currently active :class:`DebugContext` (from a ``frame`` /
    ``as_active`` block), or ``None``.

    This is how operations such as ``rasterize`` / ``datashade`` locate
    the correct per-instance context without requiring it as an explicit
    argument.
    """
    return _active_debug_context.get()


def resolve_context(preferred: DebugContext | None = None) -> DebugContext:
    """Resolve the appropriate debug context to write to.

    Priority:
    1. An explicitly provided *preferred* context, if enabled.
    2. The currently active context (set via :meth:`DebugContext.as_active` /
       :meth:`DebugContext.frame`), if enabled.
    3. The global ``hv.debug`` singleton.

    Always returns a :class:`DebugContext` instance (even if disabled).
    """
    if preferred is not None and preferred.enabled:
        return preferred
    active = _active_debug_context.get()
    if active is not None and active.enabled:
        return active
    return debug


def get_active_owner() -> tuple[str, str] | None:
    """Return the active frame owner (``owner_id``, ``owner_type``) set
    by the innermost :meth:`DebugContext.as_active` call, or ``None``."""
    return _active_frame_owner.get()


@contextmanager
def debug_frame(
    frame_id: str | None = None,
    *,
    context: DebugContext | None = None,
    owner_id: str | None = None,
    owner_type: str | None = None,
) -> Iterator[dict]:
    """Convenience context-manager that opens a frame on the appropriate context.

    Uses :func:`resolve_context` to pick a context.

    Parameters
    ----------
    frame_id : str, optional
        Explicit frame id.
    context : DebugContext, optional
        Preferred context to record into.
    owner_id / owner_type : str, optional
        Owner identity to attach to every record inside this block.
    """
    ctx = resolve_context(context)
    with ctx.frame(
        frame_id,
        owner_id=owner_id,
        owner_type=owner_type,
    ) as frame_info:
        yield frame_info


def enable_debug() -> None:
    """Enable the **global** debug context (``hv.debug``).

    For per-instance debugging, set ``dmap.debug_context.enabled = True``.
    """
    debug.enabled = True


def disable_debug() -> None:
    """Disable the **global** debug context."""
    debug.enabled = False


def get_debug_context() -> DebugContext:
    """Return the global debug context instance (``hv.debug``)."""
    return debug


__all__ = [
    "DebugContext",
    "debug",
    "debug_frame",
    "enable_debug",
    "disable_debug",
    "get_debug_context",
    "get_active_context",
    "get_active_owner",
    "resolve_context",
    "_active_debug_context",
    "_active_frame_owner",
    "_short_id",
]
