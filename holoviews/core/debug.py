"""Debug context for DynamicMap and datashader/rasterize operations.

Provides a unified mechanism to collect and access debugging information
across streams, operations, renderers, and backend plots.
"""

from __future__ import annotations

import threading
import time
import typing as t
from collections import defaultdict
from contextlib import contextmanager

import param

if t.TYPE_CHECKING:
    from collections.abc import Iterator


class DebugContext(param.Parameterized):
    """Unified debug context for collecting debugging information.

    Collects information from streams, operations, renderers, and backend
    plots into a single, easily accessible location.

    Information categories:
    - streams: Current stream parameter values and triggering information
    - cache: Cache hit/miss information
    - operation: Range clipping, sampling resolution, aggregation dimensions
    - render: Actual rendering ranges from the backend
    - timing: Timing information for each stage
    """

    enabled = param.Boolean(
        default=False,
        doc="""
        Whether debugging information collection is enabled.
        When disabled, all operations are no-ops for minimal overhead.""",
    )

    max_frames = param.Integer(
        default=10,
        bounds=(1, 1000),
        doc="""
        Maximum number of frames to retain debug information for.
        Older frames are automatically evicted (FIFO).""",
    )

    def __init__(self, **params):
        super().__init__(**params)
        self._frames: list[dict] = []
        self._current_frame: dict | None = None
        self._lock = threading.Lock()
        self._frame_counter = 0

    @contextmanager
    def frame(self, frame_id: str | None = None) -> Iterator[dict]:
        """Context manager for a single frame's debug information.

        Parameters
        ----------
        frame_id : str, optional
            Unique identifier for the frame. Auto-generated if not provided.

        Yields
        ------
        dict
            The frame's debug information dictionary.
        """
        if not self.enabled:
            yield {}
            return

        if frame_id is None:
            frame_id = f"frame_{self._frame_counter}"
            self._frame_counter += 1

        frame_info = {
            "frame_id": frame_id,
            "timestamp": time.time(),
            "streams": {},
            "cache": {},
            "operation": {},
            "render": {},
            "timing": {},
            "redraw_reason": None,
        }

        self._current_frame = frame_info
        start_time = time.time()

        try:
            yield frame_info
        finally:
            frame_info["timing"]["total"] = time.time() - start_time
            with self._lock:
                self._frames.append(frame_info)
                if len(self._frames) > self.max_frames:
                    self._frames.pop(0)
            self._current_frame = None

    def record_streams(self, stream_info: dict) -> None:
        """Record stream parameter information for the current frame.

        Parameters
        ----------
        stream_info : dict
            Dictionary containing stream information with keys like:
            - 'parameters': Current parameter values per stream
            - 'triggered': List of streams that triggered this frame
            - 'changes': Parameter changes since last frame
        """
        if not self.enabled or self._current_frame is None:
            return
        self._current_frame["streams"].update(stream_info)

    def record_cache(
        self,
        key: t.Any,
        hit: bool,
        cache_size: int | None = None,
        reason: str | None = None,
    ) -> None:
        """Record cache hit/miss information for the current frame.

        Parameters
        ----------
        key : Any
            The cache key being looked up.
        hit : bool
            Whether the key was found in the cache.
        cache_size : int, optional
            Current size of the cache.
        reason : str, optional
            Reason for cache miss (e.g., "key not in cache", "memoization disabled").
        """
        if not self.enabled or self._current_frame is None:
            return
        cache_info = self._current_frame["cache"]
        cache_info.setdefault("history", []).append(
            {"key": key, "hit": hit, "reason": reason, "timestamp": time.time()}
        )
        if cache_size is not None:
            cache_info["size"] = cache_size
        if not hit:
            cache_info["last_miss_reason"] = reason

    def record_operation(
        self,
        op_name: str,
        op_info: dict,
    ) -> None:
        """Record operation information for the current frame.

        Parameters
        ----------
        op_name : str
            Name of the operation (e.g., "rasterize", "datashade").
        op_info : dict
            Operation information with keys like:
            - 'input_range': Original input range (x_range, y_range)
            - 'clipped_range': Range after clipping to data bounds
            - 'sampling_resolution': (x_sampling, y_sampling)
            - 'aggregation_size': (width, height) of aggregation
            - 'aggregator': Type of aggregator used
            - 'element_type': Type of element being processed
            - 'data_points': Number of data points processed
        """
        if not self.enabled or self._current_frame is None:
            return
        ops = self._current_frame["operation"].setdefault("operations", [])
        op_entry = {"name": op_name, "timestamp": time.time(), **op_info}
        ops.append(op_entry)

    def record_render(
        self,
        backend: str,
        render_info: dict,
    ) -> None:
        """Record rendering information from the backend.

        Parameters
        ----------
        backend : str
            Name of the backend (e.g., "bokeh", "matplotlib", "plotly").
        render_info : dict
            Render information with keys like:
            - 'actual_range': Actual range used for rendering
            - 'plot_size': (width, height) of the plot in pixels
            - 'pixel_ratio': Device pixel ratio
            - 'render_time': Time taken to render
        """
        if not self.enabled or self._current_frame is None:
            return
        self._current_frame["render"][backend] = {
            "timestamp": time.time(),
            **render_info,
        }

    def record_redraw_reason(self, reason: str) -> None:
        """Record the reason for triggering a redraw.

        Parameters
        ----------
        reason : str
            Description of why the redraw was triggered
            (e.g., "stream X updated", "range changed", "data updated").
        """
        if not self.enabled or self._current_frame is None:
            return
        self._current_frame["redraw_reason"] = reason

    def record_timing(self, stage: str, duration: float) -> None:
        """Record timing information for a processing stage.

        Parameters
        ----------
        stage : str
            Name of the processing stage.
        duration : float
            Duration in seconds.
        """
        if not self.enabled or self._current_frame is None:
            return
        self._current_frame["timing"][stage] = duration

    def get_frames(self, n: int | None = None) -> list[dict]:
        """Get the collected debug information for frames.

        Parameters
        ----------
        n : int, optional
            Number of most recent frames to return.
            Returns all frames if not specified.

        Returns
        -------
        list[dict]
            List of frame debug information dictionaries.
        """
        with self._lock:
            frames = list(self._frames)
        if n is not None:
            return frames[-n:]
        return frames

    def get_latest_frame(self) -> dict | None:
        """Get the most recent frame's debug information.

        Returns
        -------
        dict or None
            Most recent frame debug info, or None if no frames collected.
        """
        with self._lock:
            return self._frames[-1] if self._frames else None

    def clear(self) -> None:
        """Clear all collected debug information."""
        with self._lock:
            self._frames.clear()
            self._frame_counter = 0

    def summary(self, n: int = 1) -> str:
        """Generate a human-readable summary of debug information.

        Parameters
        ----------
        n : int, optional
            Number of recent frames to include in summary.

        Returns
        -------
        str
            Formatted summary string.
        """
        if not self.enabled:
            return "Debug context is disabled. Set debug.enabled=True to enable."

        frames = self.get_frames(n)
        if not frames:
            return "No debug information collected yet."

        lines = ["=" * 70, "HoloViews Debug Context Summary", "=" * 70, ""]

        for i, frame in enumerate(reversed(frames)):
            lines.append(f"Frame {len(frames) - i}: {frame['frame_id']}")
            lines.append(f"  Timestamp: {time.ctime(frame['timestamp'])}")
            lines.append(f"  Total time: {frame['timing'].get('total', 'N/A'):.4f}s")

            if frame.get("redraw_reason"):
                lines.append(f"  Redraw reason: {frame['redraw_reason']}")

            if frame["streams"]:
                lines.append("  Streams:")
                for sname, sinfo in frame["streams"].get("parameters", {}).items():
                    lines.append(f"    {sname}: {sinfo}")
                triggered = frame["streams"].get("triggered", [])
                if triggered:
                    lines.append(f"    Triggered: {triggered}")

            if frame["cache"]:
                lines.append("  Cache:")
                history = frame["cache"].get("history", [])
                if history:
                    last = history[-1]
                    lines.append(
                        f"    Last access: {'HIT' if last['hit'] else 'MISS'} "
                        f"for key {last['key']}"
                    )
                    if not last["hit"] and last.get("reason"):
                        lines.append(f"      Reason: {last['reason']}")
                if "size" in frame["cache"]:
                    lines.append(f"    Cache size: {frame['cache']['size']}")

            if frame["operation"].get("operations"):
                lines.append("  Operations:")
                for op in frame["operation"]["operations"]:
                    lines.append(f"    {op['name']}:")
                    if "input_range" in op:
                        lines.append(f"      Input range: {op['input_range']}")
                    if "clipped_range" in op:
                        lines.append(f"      Clipped range: {op['clipped_range']}")
                    if "sampling_resolution" in op:
                        lines.append(f"      Sampling resolution: {op['sampling_resolution']}")
                    if "aggregation_size" in op:
                        lines.append(f"      Aggregation size: {op['aggregation_size']}")
                    if "aggregator" in op:
                        lines.append(f"      Aggregator: {op['aggregator']}")
                    if "data_points" in op:
                        lines.append(f"      Data points: {op['data_points']}")

            if frame["render"]:
                lines.append("  Render:")
                for backend, rinfo in frame["render"].items():
                    lines.append(f"    {backend}:")
                    if "actual_range" in rinfo:
                        lines.append(f"      Actual range: {rinfo['actual_range']}")
                    if "plot_size" in rinfo:
                        lines.append(f"      Plot size: {rinfo['plot_size']}")
                    if "pixel_ratio" in rinfo:
                        lines.append(f"      Pixel ratio: {rinfo['pixel_ratio']}")
                    if "render_time" in rinfo:
                        lines.append(f"      Render time: {rinfo['render_time']:.4f}s")

            lines.append("")

        return "\n".join(lines)

    def _repr_html_(self) -> str:
        """HTML representation for Jupyter notebooks."""
        if not self.enabled:
            return (
                "<div style='padding: 10px; background: #fff3cd; "
                "border: 1px solid #ffeeba; border-radius: 4px;'>"
                "<strong>Debug Context</strong>: Disabled. "
                "Set <code>debug.enabled=True</code> to enable."
                "</div>"
            )

        frames = self.get_frames(5)
        if not frames:
            return (
                "<div style='padding: 10px; background: #d1ecf1; "
                "border: 1px solid #bee5eb; border-radius: 4px;'>"
                "<strong>Debug Context</strong>: No debug information collected yet."
                "</div>"
            )

        html = [
            "<div style='font-family: monospace; font-size: 12px; "
            "max-height: 500px; overflow-y: auto;'>",
            "<h4 style='margin: 0 0 10px 0;'>HoloViews Debug Context</h4>",
        ]

        for i, frame in enumerate(reversed(frames)):
            frame_num = len(frames) - i
            bg = "#f8f9fa" if i % 2 == 0 else "#ffffff"
            html.append(
                f"<div style='padding: 8px; margin-bottom: 8px; "
                f"background: {bg}; border: 1px solid #dee2e6; "
                f"border-radius: 4px;'>"
            )
            html.append(
                f"<div style='font-weight: bold; color: #007bff;'>"
                f"Frame {frame_num}: {frame['frame_id']}</div>"
            )
            html.append(
                f"<div style='color: #6c757d; font-size: 11px;'>"
                f"{time.ctime(frame['timestamp'])} | "
                f"Total: {frame['timing'].get('total', 'N/A'):.4f}s"
                "</div>"
            )

            if frame.get("redraw_reason"):
                html.append(
                    f"<div style='margin-top: 5px;'>"
                    f"<span style='color: #fd7e14;'>Redraw:</span> "
                    f"{frame['redraw_reason']}"
                    "</div>"
                )

            if frame["streams"]:
                html.append("<div style='margin-top: 5px;'><strong>Streams:</strong></div>")
                html.append("<ul style='margin: 2px 0 0 20px; padding: 0;'>")
                for sname, sinfo in frame["streams"].get("parameters", {}).items():
                    html.append(f"<li><code>{sname}</code>: {sinfo}</li>")
                triggered = frame["streams"].get("triggered", [])
                if triggered:
                    html.append(
                        f"<li style='color: #dc3545;'>Triggered: {triggered}</li>"
                    )
                html.append("</ul>")

            if frame["cache"].get("history"):
                html.append("<div style='margin-top: 5px;'><strong>Cache:</strong></div>")
                html.append("<ul style='margin: 2px 0 0 20px; padding: 0;'>")
                for entry in frame["cache"]["history"][-3:]:
                    status = "✓ HIT" if entry["hit"] else "✗ MISS"
                    color = "#28a745" if entry["hit"] else "#dc3545"
                    reason = f" ({entry['reason']})" if entry.get("reason") else ""
                    html.append(
                        f"<li><span style='color: {color};'>{status}</span> "
                        f"key: {entry['key']}{reason}</li>"
                    )
                html.append("</ul>")

            if frame["operation"].get("operations"):
                html.append("<div style='margin-top: 5px;'><strong>Operations:</strong></div>")
                for op in frame["operation"]["operations"]:
                    html.append(
                        f"<div style='margin-left: 10px; "
                        f"padding: 4px; background: #e9ecef; "
                        f"border-radius: 3px; margin-top: 2px;'>"
                    )
                    html.append(f"<div><code>{op['name']}</code></div>")
                    op_details = []
                    if "input_range" in op:
                        op_details.append(f"Input: {op['input_range']}")
                    if "clipped_range" in op:
                        op_details.append(f"Clipped: {op['clipped_range']}")
                    if "aggregation_size" in op:
                        op_details.append(f"Size: {op['aggregation_size']}")
                    if op_details:
                        html.append(
                            f"<div style='font-size: 11px; color: #495057;'>"
                            f"{' | '.join(op_details)}"
                            f"</div>"
                        )
                    html.append("</div>")

            if frame["render"]:
                html.append("<div style='margin-top: 5px;'><strong>Render:</strong></div>")
                html.append("<ul style='margin: 2px 0 0 20px; padding: 0;'>")
                for backend, rinfo in frame["render"].items():
                    details = []
                    if "actual_range" in rinfo:
                        details.append(f"Range: {rinfo['actual_range']}")
                    if "plot_size" in rinfo:
                        details.append(f"Size: {rinfo['plot_size']}")
                    html.append(f"<li><strong>{backend}</strong>: {' | '.join(details)}</li>")
                html.append("</ul>")

            html.append("</div>")

        html.append("</div>")
        return "".join(html)

    def __repr__(self) -> str:
        return self.summary(1)


# Global debug context instance
debug = DebugContext(name="holoviews_debug")


@contextmanager
def debug_frame(frame_id: str | None = None) -> Iterator[dict]:
    """Context manager for collecting debug information for a single frame.

    Parameters
    ----------
    frame_id : str, optional
        Unique identifier for the frame.

    Yields
    ------
    dict
        Frame debug information dictionary.

    Examples
    --------
    >>> with debug_frame("my_frame") as frame_info:
    ...     frame_info["custom_key"] = "custom_value"
    """
    with debug.frame(frame_id) as frame_info:
        yield frame_info


def enable_debug() -> None:
    """Enable debug information collection."""
    debug.enabled = True


def disable_debug() -> None:
    """Disable debug information collection."""
    debug.enabled = False


def get_debug_context() -> DebugContext:
    """Get the global debug context instance.

    Returns
    -------
    DebugContext
        The global debug context instance.
    """
    return debug


__all__ = [
    "DebugContext",
    "debug",
    "debug_frame",
    "enable_debug",
    "disable_debug",
    "get_debug_context",
]
