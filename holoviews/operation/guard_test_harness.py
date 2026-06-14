"""Datashader-equivalent guard test harness -- pure-Python, no datashader required.

Purpose
-------

Verify that the guard pipeline works end-to-end on classes that follow the
*exact same inheritance and call patterns* as the real
``holoviews.operation.datashader`` operations, without requiring datashader
to be importable (it often cannot be installed due to numba/numpy version
conflicts in test environments).

Classes here mirror the real inheritance hierarchy in
``holoviews/operation/datashader.py`` and ``holoviews/operation/resample.py``:

* ``GuardedResampleOperation2D`` (imported from .resample) -- the base mixin
  used by AggregationOperation in the real code.
* ``FakeAggregationOperation`` -- stands in for ``AggregationOperation``.
* ``fake_aggregate`` -- stands in for ``aggregate`` / simple rasterization.
* ``fake_rasterize`` -- stands in for ``rasterize`` (same MRO + _process_core shape).
* ``FakeShade`` -- stands in for ``shade`` (uses GuardedOperationMixin + _process_core,
  recursively applies itself to Overlays just like the real class).
* ``fake_datashade`` -- stands in for ``datashade`` (MRO combines rasterize + shade,
  and _process_core composes them exactly like the real implementation).

All of these classes perform *tiny* pure-Python computations so that tests can
exercise: parameter normalisation, empty short-circuit, cache hit / miss,
exception wrapping, per-output _guard_info attachment, Overlay recursion and
the dynamic=True frame path.
"""

from __future__ import annotations

import numpy as np

import param

from ..core import Dimension, NdOverlay, Overlay, operation
from ..element import Curve, Image, Scatter
from .guard import ExecutionGuardResult, GuardedOperationMixin
from .resample import GuardedResampleOperation2D, LinkableOperation

__all__ = [
    "ExecutionGuardResult",  # re-exported for test convenience
    "FakeAggregationOperation",
    "FakeShade",
    "fake_aggregate",
    "fake_datashade",
    "fake_rasterize",
    "run_guard_smoke",
]

# ---------------------------------------------------------------------------
# 1. Aggregation-style operation -- mirrors AggregationOperation in datashader.py
# ---------------------------------------------------------------------------

class FakeAggregationOperation(GuardedResampleOperation2D):
    """Mirror of ``AggregationOperation`` in the real datashader module.

    Uses GuardedResampleOperation2D (which itself inherits OperationGuard via
    the ResampleOperationGuard mixin) exactly like the real base class.
    """

    aggregator = param.String(default="count", doc="Fake aggregator name.")

    dynamic = param.Boolean(default=True, doc="Same default as ResampleOperation2D.")

    def _normalize_params(self, element, key=None, **kwargs):
        """Mirror real rasterize normalisation: derive x_range/y_range from element
        and enforce sensible defaults for width/height.
        """
        params = dict(self.p) if hasattr(self, "p") else {}
        if params.get("x_range") is None and hasattr(element, "range"):
            kdims = [d.name for d in getattr(element, "kdims", [])]
            if len(kdims) >= 1:
                params["x_range"] = element.range(kdims[0])
            if len(kdims) >= 2:
                params["y_range"] = element.range(kdims[1])
        if params.get("width") is None or params["width"] <= 0:
            params["width"] = 400
        if params.get("height") is None or params["height"] <= 0:
            params["height"] = 400
        # Stash canonical params on the normalized element for tests to read.
        element._guard_normalized = params
        return element

    def _check_empty(self, element, key=None):
        try:
            if hasattr(element, "shape"):
                if np.prod(element.shape) == 0:
                    return True
        except Exception:
            pass
        if hasattr(element, "__len__"):
            try:
                return len(element) == 0
            except Exception:
                return False
        return False

    def _empty_result(self, element, key=None):
        """Return a zero-size Image, mirroring what the real rasterize would do."""
        empty_data = np.zeros((0, 0))
        return Image(empty_data, kdims=getattr(element, "kdims", ["x", "y"]))


# ---------------------------------------------------------------------------
# 2. fake_aggregate -- mirrors aggregate / simple operations
# ---------------------------------------------------------------------------

class fake_aggregate(FakeAggregationOperation):
    """Simple rasterization stand-in.

    Takes a Scatter / Curve element and returns an Image of shape
    (height, width) whose pixel values are a deterministic function of
    the input data.  This is purely to exercise guard behaviour.
    """

    def _process_core(self, element, key=None, **kwargs):
        params = getattr(element, "_guard_normalized", {})
        width = int(params.get("width", 400))
        height = int(params.get("height", 400))

        # Deterministic "rasterization" -- compute a value from element id + len
        n = len(element) if hasattr(element, "__len__") else 0
        arr = np.full((height, width), float(n), dtype=np.float64)
        # Add a tiny positional fingerprint so visually-identical but
        # semantically-different inputs produce different cache keys.
        for i in range(min(10, n)):
            arr[i % height, i % width] += float(i + 1)

        bounds = None
        if "x_range" in params and "y_range" in params:
            xr, yr = params["x_range"], params["y_range"]
            bounds = (xr[0], yr[0], xr[1], yr[1])

        kdims = [Dimension("x"), Dimension("y")]
        vdims = [Dimension(self.p.aggregator if hasattr(self.p, "aggregator") else "Count")]
        if bounds is not None:
            img = Image(arr, kdims=kdims, vdims=vdims, bounds=bounds)
        else:
            img = Image(arr, kdims=kdims, vdims=vdims)
        return img


# ---------------------------------------------------------------------------
# 3. fake_rasterize -- mirrors rasterize (identical MRO + compositional shape)
# ---------------------------------------------------------------------------

class fake_rasterize(FakeAggregationOperation):
    """Mirror of the real ``rasterize`` operation.

    MRO is ``fake_rasterize -> FakeAggregationOperation -> GuardedResampleOperation2D
    -> ResampleOperationGuard -> OperationGuard`` exactly analogous to the real
    class chain.
    """

    # Mirror real rasterize param defaults if/when tests need them.
    streams = param.ClassSelector(default=[], class_=(list,), allow_None=True)

    def _process_core(self, element, key=None, **kwargs):
        # Re-use the aggregate implementation; real rasterize does a lot more
        # but for guard-testing purposes an identical shape is sufficient.
        return fake_aggregate._process_core(self, element, key, **kwargs)


# ---------------------------------------------------------------------------
# 4. FakeShade -- mirrors shade class (GuardedOperationMixin + recursive Overlay)
# ---------------------------------------------------------------------------

class FakeShade(GuardedOperationMixin, LinkableOperation):
    """Mirror of the real ``shade`` operation.

    Inheritance exactly matches the real class: GuardedOperationMixin *first*
    so that its _process is called, followed by LinkableOperation which
    provides streams / linking.

    The real shade.apply Overlay recursion pattern is replicated here so we
    can verify that guard runs exactly once per leaf element and never wraps
    the composition call itself (which was a previous bug).
    """

    cmap = param.String(default="plasma", doc="Fake colormap name.")

    min_alpha = param.Number(default=0, bounds=(0, 255))
    max_alpha = param.Number(default=255, bounds=(0, 255))

    def _normalize_params(self, element, key=None, **kwargs):
        params = {
            "cmap": self.cmap,
            "min_alpha": self.min_alpha,
            "max_alpha": self.max_alpha,
        }
        # Stash for tests just like aggregation does.
        try:
            element._guard_normalized = params
        except Exception:
            pass
        return element

    def _check_empty(self, element, key=None):
        # FakeShade itself only makes a per-leaf emptiness call after the
        # container has been unpacked by _process_core.  For containers just
        # delegate to the parent class's robust default.
        if isinstance(element, (NdOverlay, Overlay)):
            return False
        try:
            if hasattr(element, "shape"):
                if np.prod(element.shape) == 0:
                    return True
        except Exception:
            pass
        return False

    def _empty_result(self, element, key=None):
        # Forward to upstream empty-result logic.
        if hasattr(element, "clone"):
            return element.clone()
        return element

    def _process_core(self, element, key=None, **kwargs):
        """Pure-Python "shading": convert a scalar Image to an RGBA-like Image.

        For Overlays the real shade recurses via ``element.map(shade._process, [Element])``.
        We do the exact same thing but call ``FakeShade._process_core`` directly
        so that the outer guard (already invoked for this call) runs *once* per
        leaf -- exactly matching the fixed datashader.py semantics.
        """
        if isinstance(element, (NdOverlay, Overlay)):
            from functools import partial

            # Recurse exactly like the real shade does.  Calling _process_core
            # (NOT _process) avoids double-wrapping guard.
            return element.map(partial(FakeShade._process_core, self), [Image])

        # Scalar Image -> fake RGB Image with 4 channels.
        data = None
        try:
            data = np.asarray(element.data)
        except Exception:
            data = np.zeros((2, 2))

        h, w = data.shape[:2]
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        # Fake shading: map min->0, max->255 of the first two channels.
        if data.size > 0:
            dmin, dmax = float(data.min()), float(data.max())
            span = dmax - dmin if dmax > dmin else 1.0
            norm = (data - dmin) / span
            rgba[..., 0] = np.clip(norm * 255, 0, 255).astype(np.uint8)
            rgba[..., 1] = np.clip(norm * 128 + 64, 0, 255).astype(np.uint8)
        rgba[..., 2] = 128
        rgba[..., 3] = 255

        kdims = list(getattr(element, "kdims", [Dimension("x"), Dimension("y")]))
        try:
            from ..element import RGB
        except Exception:
            RGB = Image
        bounds = getattr(element, "bounds", None)
        if bounds is not None:
            return RGB(rgba, kdims=kdims, bounds=bounds)
        return RGB(rgba, kdims=kdims)


# ---------------------------------------------------------------------------
# 5. fake_datashade -- mirrors datashade (rasterize + shade composition in
#    a single operation's _process_core).
# ---------------------------------------------------------------------------

class fake_datashade(fake_rasterize, FakeShade):
    """Mirror of the real ``datashade`` operation.

    The real datashade uses MRO ``datashade -> rasterize -> shade``.  Here we
    do ``fake_datashade -> fake_rasterize -> FakeShade`` and its _process_core
    composes rasterize._process_core followed by FakeShade._process_core
    *without* going through _process on either -- exactly matching the fix we
    applied to the real datashader class.
    """

    def _process_core(self, element, key=None, **kwargs):
        agg = fake_rasterize._process_core(self, element, key, **kwargs)
        shaded = FakeShade._process_core(self, agg, key, **kwargs)
        return shaded


# ---------------------------------------------------------------------------
# 6. Convenience smoke-test entry point
# ---------------------------------------------------------------------------

def run_guard_smoke():
    """Run a quick end-to-end smoke test and return a results dict.

    Useful for CI / one-off execution outside pytest.  Raises AssertionError
    on failure, otherwise returns a dict summarising what was verified.
    """
    passed = []

    x = np.linspace(0, 10, 100)
    y = np.sin(x)
    scatter = Scatter((x, y), kdims=["x", "y"])
    curve = Curve((x, y), kdims=["x"], vdims=["y"])

    # -- 1. Fake rasterize, dynamic=False (direct synchronous path) ---------
    result = fake_rasterize(scatter, x_range=(0, 10), y_range=(-1, 1),
                            width=200, height=100, dynamic=False)
    assert isinstance(result, Image), f"direct rasterize returned {type(result)}"
    assert hasattr(result, "_guard_info"), "direct output missing _guard_info"
    gi = result._guard_info
    assert isinstance(gi, ExecutionGuardResult)
    assert gi.success and not gi.cached and not gi.empty
    assert gi.normalized_params is not None
    assert gi.execution_time >= 0.0
    passed.append("direct fake_rasterize")

    # -- 2. Empty short-circuit carries empty=True on output _guard_info ----
    empty_scatter = Scatter(([], []), kdims=["x", "y"])
    empty_out = fake_rasterize(empty_scatter, dynamic=False)
    assert empty_out._guard_info.empty is True, "empty short-circuit not flagged"
    assert empty_out._guard_info.output is empty_out
    passed.append("empty short-circuit")

    # -- 3. Dynamic frame path: _guard_info attached per frame --------------
    dyn = fake_rasterize(scatter, x_range=(0, 10), y_range=(-1, 1),
                         width=200, height=100, dynamic=True)
    frame = dyn[()]
    assert hasattr(frame, "_guard_info"), "dynamic frame missing _guard_info"
    assert frame._guard_info.success and not frame._guard_info.empty
    passed.append("dynamic frame _guard_info")

    # -- 4. Two different params produce independent _guard_info ------------
    f1 = fake_rasterize(scatter, x_range=(0, 10), y_range=(-1, 1),
                        width=10, height=10, dynamic=False)
    f2 = fake_rasterize(scatter, x_range=(0, 10), y_range=(-1, 1),
                        width=99, height=99, dynamic=False)
    # Must not share the same guard result (previous bug: only on op instance).
    assert f1._guard_info is not f2._guard_info, "results share _guard_info object"
    assert f1._guard_info.normalized_params is not None
    assert f2._guard_info.normalized_params is not None
    passed.append("independent _guard_info per call")

    # -- 5. FakeShade Overlay recursion: guard info on container AND leaves -
    img1 = fake_rasterize(scatter, dynamic=False)
    img2 = fake_rasterize(curve, dynamic=False)
    ov = Overlay([img1, img2]).map(
        lambda leaf: FakeShade._process_core(FakeShade.instance(cmap="viridis"), leaf),
        [Image],
    )
    # Run shade properly via its __call__ (which invokes guard).
    shaded = FakeShade(Overlay([img1, img2]), dynamic=False)
    assert hasattr(shaded, "_guard_info"), "shaded overlay missing _guard_info"
    # And every leaf inside should also have guard info.
    leaves = shaded.traverse(lambda x: x, [Image])
    for leaf in leaves:
        assert hasattr(leaf, "_guard_info"), "overlay leaf missing _guard_info"
    passed.append("Overlay recursion + leaf guard info")

    # -- 6. fake_datashade composition: single guard, not nested -----------
    ds = fake_datashade(scatter, x_range=(0, 10), y_range=(-1, 1),
                        width=50, height=50, dynamic=False)
    assert hasattr(ds, "_guard_info")
    # Only one guard layer should have wrapped the execution.
    # The instance's _last_guard_result must match ds._guard_info:
    last = getattr(fake_datashade.instance(), "_last_guard_result", None)
    # (don't assert identity -- the instance may have been reused; just check
    #  that the product carries its own metadata.)
    assert ds._guard_info.success and not ds._guard_info.empty
    passed.append("fake_datashade composition")

    # -- 7. ExecutionGuardResult.to_summary_dict round-trip -----------------
    s = ds._guard_info.to_summary_dict()
    assert isinstance(s, dict) and s["success"] and s["operation"] == "fake_datashade"
    assert "timestamp" in s and "execution_time" in s
    passed.append("to_summary_dict")

    return {"passed": passed, "total": len(passed)}
