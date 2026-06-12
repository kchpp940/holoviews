"""Deep trace of lifecycle phase execution and object mutation."""
import holoviews as hv
from holoviews.plotting.lifecycle import LifecyclePhase, LifecycleHook, LifecycleContext
import copy


class DeepTraceHook(LifecycleHook):
    """Records: phase order, object presence, and object mutations between phases."""

    def __init__(self):
        super().__init__()
        self.phase_log = []
        self.snapshots = {}

    def should_run(self, phase, when, ctx):
        return True

    def _snapshot(self, ctx):
        snap = {}
        for attr in ["figure", "layout", "axes", "glyphs", "legend", "colorbar", "tools"]:
            val = getattr(ctx, attr, None)
            if val is not None:
                if attr == "axes":
                    if isinstance(val, dict):
                        snap["axes_keys"] = list(val.keys())
                        snap["axes_types"] = {k: type(v).__name__ for k, v in val.items()}
                    elif isinstance(val, tuple):
                        snap["axes_len"] = len(val)
                        snap["axes_types"] = [type(v).__name__ for v in val]
                    else:
                        snap["axes_type"] = type(val).__name__
                elif attr == "tools":
                    if isinstance(val, dict):
                        snap["tools_keys"] = list(val.keys())
                        for k, v in val.items():
                            if v is not None:
                                snap[f"tool_{k}_type"] = type(v).__name__
                    else:
                        snap["tools_type"] = type(val).__name__
                elif attr == "glyphs" and isinstance(val, dict):
                    snap["glyphs_keys"] = list(val.keys())
                elif attr == "legend":
                    snap["legend_type"] = type(val).__name__
                    snap["legend_is_none"] = val is None
                elif attr == "colorbar":
                    snap["colorbar_type"] = type(val).__name__
                    snap["colorbar_is_none"] = val is None
                else:
                    snap[f"{attr}_type"] = type(val).__name__
        # Also check self.handles for backend-specific objects
        if ctx.plot is not None:
            handles_keys = list(ctx.plot.handles.keys())
            relevant = [k for k in handles_keys if any(
                kw in k.lower() for kw in ["legend", "colorbar", "hover", "tool", "axis", "glyph", "source"]
            )]
            snap["handles_relevant"] = relevant
        return snap

    def run(self, phase, when, ctx):
        key = f"{phase.name}[{when}]"
        snap = self._snapshot(ctx)
        self.phase_log.append(key)
        self.snapshots[key] = snap

        # Check axes state specifically
        if ctx.axes is not None and "xaxis" in ctx.axes if isinstance(ctx.axes, dict) else False:
            ax = ctx.axes["xaxis"]
            if hasattr(ax, "axis_label"):
                snap["xaxis_label"] = ax.axis_label
            elif hasattr(ax, "get_xlabel"):
                snap["xaxis_label"] = ax.get_xlabel()
            elif isinstance(ax, dict):
                snap["xaxis_label"] = ax.get("title", {}).get("text", "") if isinstance(ax.get("title"), dict) else ax.get("title", "")

        return ctx


def trace_backend(backend, element, element_name):
    print(f"\n{'=' * 80}")
    print(f"BACKEND: {backend.upper()}  |  ELEMENT: {element_name}")
    print(f"{'=' * 80}")

    hv.extension(backend, logo=False)
    hv.output(backend=backend)
    hook = DeepTraceHook()
    renderer = hv.renderer(backend)
    renderer.lifecycle_hooks = [hook]

    try:
        plot = renderer.get_plot(element)
        fig = renderer.get_plot_state(plot)
    finally:
        renderer.lifecycle_hooks = []

    print(f"\nPhase Execution Order ({len(hook.phase_log)} phases):")
    for i, p in enumerate(hook.phase_log):
        snap = hook.snapshots.get(p, {})
        summary_parts = []
        for k in ["axes_keys", "axes_len", "glyphs_keys", "tools_keys",
                   "legend_type", "colorbar_type", "handles_relevant", "xaxis_label"]:
            if k in snap:
                summary_parts.append(f"{k}={snap[k]}")
        summary = " | ".join(summary_parts) if summary_parts else "(no tracked objects)"
        print(f"  {i + 1:2d}. {p:<30s}  {summary}")

    # Check object availability consistency
    print(f"\nObject Availability Matrix:")
    objects = ["figure", "layout", "axes", "glyphs", "legend", "colorbar", "tools"]
    header = f"  {'Phase':<25s}" + "".join(f"{o:>10s}" for o in objects)
    print(header)
    print("  " + "-" * (25 + 10 * len(objects)))
    for p in hook.phase_log:
        snap = hook.snapshots.get(p, {})
        row = f"  {p:<25s}"
        for o in objects:
            present = "✓" if snap.get(f"{o}_type") or snap.get(f"{o}_keys") or snap.get(f"{o}_len") else " "
            if o == "legend" and not snap.get("legend_is_none", True):
                present = "✓"
            elif o == "legend":
                present = " " if snap.get("legend_is_none", True) else "✓"
            if o == "colorbar" and not snap.get("colorbar_is_none", True):
                present = "✓"
            elif o == "colorbar":
                present = " " if snap.get("colorbar_is_none", True) else "✓"
            row += f"{present:>10s}"
        print(row)

    return hook


import numpy as np

# ---- Test elements (created with defaults, no opts before extension load) ----

# Simple element (no legend)
curve_simple = hv.Curve([1, 2, 3])

# Overlay with legend
curve1 = hv.Curve([1, 2, 3], label="A")
curve2 = hv.Curve([3, 2, 1], label="B")
overlay = curve1 * curve2

# Layout
layout = curve1 + curve2

# GridSpace
grid = hv.GridSpace({i: hv.Curve([i, i + 1, i + 2], label=f"C{i}") for i in range(4)}, kdims=["x"])

# Element with hover (created without opts)
points_base = hv.Points([(0, 0), (1, 1), (2, 2)], label="Pts")


# Helper to create backend-specific elements
def get_element(backend, name):
    if name == "Curve (simple)":
        return hv.Curve([1, 2, 3])
    elif name == "Overlay (2 curves with labels)":
        return hv.Curve([1, 2, 3], label="A") * hv.Curve([3, 2, 1], label="B")
    elif name == "Layout (2 curves)":
        return hv.Curve([1, 2, 3], label="A") + hv.Curve([3, 2, 1], label="B")
    elif name == "Points with hover":
        return hv.Points([(0, 0), (1, 1), (2, 2)], label="Pts").opts(tools=["hover"])
    else:
        return hv.Curve([1, 2, 3])


# Run traces
for backend in ["bokeh", "matplotlib", "plotly"]:
    trace_backend(backend, get_element(backend, "Curve (simple)"), "Curve (simple)")
    trace_backend(backend, get_element(backend, "Overlay (2 curves with labels)"), "Overlay (2 curves with labels)")
    trace_backend(backend, get_element(backend, "Layout (2 curves)"), "Layout (2 curves)")
    if backend == "bokeh":  # hover is bokeh-specific for now
        trace_backend(backend, get_element(backend, "Points with hover"), "Points with hover")
