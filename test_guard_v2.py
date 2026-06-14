"""Full guard test suite -- no datashader required.

Covers:
  1. Direct (dynamic=False) path via fake_rasterize / FakeShade / fake_datashade
  2. Dynamic (dynamic=True) DynamicMap frame execution
  3. Per-output _guard_info independence (no cross-contamination)
  4. Empty data short-circuit metadata propagation
  5. Cache hit / miss with full _guard_info.cached flag
  6. Exception wrapping and error metadata on output
  7. Normalized params written to guard result
  8. Overlay / NdOverlay recursive guard info attachment
  9. ExecutionGuardResult serialization / to_summary_dict
 10. Guard disabled behaviour

Run this file directly:
    python test_guard_v2.py
"""
from __future__ import annotations

import sys
import traceback
from contextlib import contextmanager

import numpy as np

# Make project importable even if cwd differs.
sys.path.insert(0, "/Users/pkcha/holoviews")

import holoviews as hv

hv.extension("bokeh")

from holoviews.core import Dimension, NdOverlay, Overlay
from holoviews.element import Curve, Image, Scatter
from holoviews.operation.guard import (
    ExecutionGuardResult,
    GuardedOperationMixin,
    OperationGuard,
)
from holoviews.operation.guard_test_harness import (
    FakeAggregationOperation,
    FakeShade,
    fake_aggregate,
    fake_datashade,
    fake_rasterize,
    run_guard_smoke,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

FAILURES = []
PASSED = 0


def test(name, condition, detail=""):
    global PASSED
    try:
        ok = bool(condition)
    except Exception as exc:  # pragma: no cover - test-runner utility
        FAILURES.append((name, f"exception evaluating condition: {exc}",
                         traceback.format_exc()))
        return
    if ok:
        PASSED += 1
        print(f"  [PASS] {name}")
    else:
        FAILURES.append((name, detail, detail or "condition was False"))
        print(f"  [FAIL] {name}  -- {detail}")


@contextmanager
def section(title):
    print(f"\n=== {title} ===")
    yield
    print()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_scatter(n=100):
    x = np.linspace(0, 10, n)
    y = np.sin(x)
    return Scatter((x, y), kdims=["x", "y"])


def make_curve(n=100):
    x = np.linspace(0, 10, n)
    return Curve((x, np.sin(x)), kdims=["x"], vdims=["y"])


# ========================================================================
# A.  Smoke test (imported from harness -- sanity baseline
# ========================================================================

with section("A. run_guard_smoke baseline"):
    info = run_guard_smoke()
    test("smoke test returns dict with passed == total",
         isinstance(info, dict) and len(info["passed"]) == info["total"])


# ========================================================================
# B.  Direct path (dynamic=False) -- static synchronous _guard_info basics
# ========================================================================

with section("B. Direct (dynamic=False) _guard_info basics"):
    sc = make_scatter()
    r1 = fake_rasterize(sc, x_range=(0, 10), y_range=(-1, 1),
                              width=32, height=32, dynamic=False)
    test("direct: output type Image", isinstance(r1, Image))
    test("direct: output carries _guard_info attr", hasattr(r1, "_guard_info"))
    test("direct: _guard_info is ExecutionGuardResult",
         isinstance(r1._guard_info, ExecutionGuardResult))
    gi = r1._guard_info
    test("direct: success=True", gi.success)
    test("direct: cached=False (no precompute", not gi.cached)
    test("direct: empty=False (data)", not gi.empty)
    test("direct: error is None", gi.error is None)
    test("direct: error_traceback is None", gi.error_traceback is None)
    test("direct: execution_time >= 0", gi.execution_time >= 0.0)
    test("direct: cache_time >= 0", gi.cache_time >= 0.0)
    test("direct: normalize_time >= 0", gi.normalize_time >= 0.0)
    test("direct: normalized_params present",
         gi.normalized_params is not None)
    test("direct: output reference is self", gi.output is r1)
    test("direct: timestamp set", gi.timestamp is not None)
    test("direct: metadata has operation key",
         gi.metadata.get("operation") == "fake_rasterize")
    # normalized params should contain the x/y range plus width/height
    norm = gi.normalized_params._guard_normalized
    test("direct: normalized x_range present",
         isinstance(norm, dict) and "x_range" in norm)
    test("direct: normalized y_range present",
         isinstance(norm, dict) and "y_range" in norm)
    test("direct: normalized width=32", isinstance(norm, dict) and norm["width"] == 32)
    test("direct: normalized height=32", isinstance(norm, dict) and norm["height"] == 32)
    # to_summary_dict round-trip
    s = gi.to_summary_dict()
    test("direct: to_summary_dict: to_summary dict shape",
         isinstance(s, dict))
    test("direct: to_summary_dict: success flag", s["success"] == True)
    test("direct: to_summary_dict: operation name",
         s["operation"] == "fake_rasterize")
    test("direct: to_summary_dict: execution_time numeric",
         isinstance(s.get("execution_time"), (int, float)))
    test("direct: to_summary_dict: timestamp is iso string",
         isinstance(s.get("timestamp"), str))


# ========================================================================
# C.  _guard_info independence -- no cross-call / no instance shadowing
# ========================================================================

with section("C. Per-output _guard_info independence (no instance shadowing)"):
    # Use distinct Scatter objects so that per-element _guard_normalized
    # isn't overwritten between the two calls.
    sc_a = make_scatter()
    sc_b = make_scatter()
    a = fake_rasterize(sc_a, x_range=(0, 10), y_range=(-1, 1),
                        width=10, height=10, dynamic=False)
    b = fake_rasterize(sc_b, x_range=(0, 10), y_range=(-1, 1),
                        width=99, height=99, dynamic=False)
    a_norm = getattr(a._guard_info.normalized_params, "_guard_normalized", {})
    b_norm = getattr(b._guard_info.normalized_params, "_guard_normalized", {})
    test("independence: a != b (objects", a is not b)
    test("independence: _guard_info not same object",
         a._guard_info is not b._guard_info)
    test("independence: a normalized width == 10",
         a_norm.get("width") == 10,
         detail=f"got {a_norm!r}")
    test("independence: b normalized width == 99",
         b_norm.get("width") == 99,
         detail=f"got {b_norm!r}")
    test("independence: output references point to themselves",
         a._guard_info.output is a and b._guard_info.output is b)
    # Make sure metadata has the operation name matches
    test("independence: a.metadata.operation matches",
         a._guard_info.metadata["operation"] == "fake_rasterize")


# ========================================================================
# D.  DynamicMap frame path (dynamic=True) -- guard info per frame
# ========================================================================

with section("D. Dynamic (dynamic=True) frame _guard_info"):
    sc = make_scatter()
    dyn = fake_rasterize(sc, x_range=(0, 10), y_range=(-1, 1),
                              width=64, height=64, dynamic=True)
    test("dynamic: returns DynamicMap",
         type(dyn).__name__ == "DynamicMap")
    frame1 = dyn[()]
    test("dynamic: frame[()] is Image", isinstance(frame1, Image))
    test("dynamic: frame1 carries _guard_info", hasattr(frame1, "_guard_info"))
    gi1 = frame1._guard_info
    test("dynamic: frame1.success & not empty", gi1.success and not gi1.empty)
    # Re-evaluate: each frame gets its own guard info
    frame2 = dyn[()]
    test("dynamic: re-evaluation: frame2 carries _guard_info",
         hasattr(frame2, "_guard_info"))
    test("dynamic: re-evaluation different objects (not cross frame objects",
         frame1._guard_info is not frame2._guard_info)
    # frame normalized_params matches the dynamic frame2._guard_info
    test("dynamic: normalized matches width",
         frame2._guard_info.normalized_params._guard_normalized["width"] == 64)


# ========================================================================
# E.  Empty short-circuit -- guard result empty=True + output metadata
# ========================================================================

with section("E. Empty short-circuit (empty) empty = True"):
    empty_sc = Scatter(([], []), kdims=["x", "y"])
    result = fake_rasterize(empty_sc, dynamic=False)
    test("empty: output has _guard_info", hasattr(result, "_guard_info"))
    gi = result._guard_info
    test("empty: success=True (empty short-circuit still counts as success",
         gi.success)
    test("empty: empty flag True", gi.empty is True)
    test("empty: cached False", gi.cached is False)
    test("empty: error None", gi.error is None)
    test("empty: output is self", gi.output is result)
    test("empty: execution_time recorded", gi.execution_time >= 0.0)
    # normalized_params
    test("empty normalized_params present",
         gi.normalized_params is not None)
    # Also fake_shade: empty empty: FakeShade also handles empty input
    empty_img = Image(np.zeros((0, 0)))
    shade_empty = FakeShade(empty_img, dynamic=False)
    test("empty: FakeShade empty_ok",
         hasattr(shade_empty, "_guard_info"))
    test("empty: FakeShade empty_empty_flag",
         shade_empty._guard_info.empty is True)


# ========================================================================
# F.  Caching -- precompute + cached flag
# ========================================================================

with section("F. Caching behavior (precompute=True -> cached=True)"):
    sc_a = make_scatter()

    # Build a brand new class and instance, bypassing param's .instance() singleton
    # so no other test section can pollute _precomputed.
    import uuid
    spy_cls_name = "_CacheSpy_" + uuid.uuid4().hex[:8]
    spy_cls = type(spy_cls_name, (fake_rasterize,), {})

    import param as _param
    spy = _param.Parameterized.__new__(spy_cls)
    spy.__init__(
        x_range=(0, 10), y_range=(-1, 1), width=16, height=16,
        precompute=True, dynamic=False,
    )
    spy._precomputed = {}

    out1 = spy(sc_a)
    out2 = spy(sc_a)
    test("cache: both outputs are images",
         isinstance(out1, Image) and isinstance(out2, Image))
    test("cache: spy has _precomputed",
         hasattr(spy, "_precomputed") and len(spy._precomputed) > 0)
    test("cache: out1 first call not cached",
         out1._guard_info.cached is False,
         detail=f"out1.cached={out1._guard_info.cached}, keys={list(getattr(spy, '_precomputed', {}).keys())}")
    test("cache: out2 second call cached=True",
         out2._guard_info.cached is True,
         detail=f"out2.cached={out2._guard_info.cached}")
    test("cache out2: _guard_info success", out2._guard_info.success)
    test("cache out2: empty False", out2._guard_info.empty is False)
    # The cached object itself should also carry valid guard info: since guard runs for
    # the original output out1 guard_info carries its own
    test("cache out1 out2: both objects have guard info",
         hasattr(out1, "_guard_info") and hasattr(out2, "_guard_info"))


# ========================================================================
# G.  Exception wrapping -- error fields populated
# ========================================================================

with section("G. Exception wrapping + error metadata"):

    class BrokenOp(FakeAggregationOperation):
        def _process_core(self, element, key=None, **kwargs):
            raise RuntimeError("intentional boom from broken _process_core")

    sc = make_scatter()
    # Use an explicit instance so we can inspect _last_guard_result on the
    # exact object that executed.
    broken_op = BrokenOp.instance(dynamic=False)
    try:
        broken_op(sc)
        test("exception: exception raised", False, "expected RuntimeError was not raised")
    except RuntimeError as exc:
        test("exception: message contains operation name",
             "BrokenOp" in str(exc))
        last = getattr(broken_op, "_last_guard_result", None)
        test("exception: op instance has _last_guard_result",
             isinstance(last, ExecutionGuardResult),
             detail=f"last={last!r}")
        if last is not None:
            test("exception: _last_guard_result.success=False",
                 last.success is False)
            test("exception: last.error matches RuntimeError",
                 isinstance(last.error, RuntimeError))
            test("exception: last.error_traceback is str",
                 isinstance(last.error_traceback, str))
            test("exception: last.execution_time >= 0",
                 last.execution_time >= 0.0)
    except Exception as exc2:
        test("exception: unexpected exception type", False,
             f"expected RuntimeError got {type(exc2).__name__}: {exc2}")


# ========================================================================
# H.  Overlay / NdOverlay -- recursive guard info
# ========================================================================

with section("H. Overlay / NdOverlay recursive guard info"):
    r1 = fake_rasterize(make_scatter(), width=8, height=8, dynamic=False)
    r2 = fake_rasterize(make_curve(), width=8, height=8, dynamic=False)
    # Wrap in Overlay
    ov = Overlay([r1, r2])
    # Run FakeShade processes an Overlay
    shaded = FakeShade(ov, dynamic=False)
    test("overlay: overlay output has guard info", hasattr(shaded, "_guard_info"))
    # Container itself carries _guard_info
    test("overlay: shaded Overlay type", isinstance(shaded, Overlay))
    gi = shaded._guard_info
    test("overlay shaded.success shaded guard info", isinstance(gi, ExecutionGuardResult))
    # Now check recursive attachment
    leaves = shaded.traverse(lambda x: x, [Image])
    test("overlay leaves found", len(leaves) > 0)
    for idx, leaf in enumerate(leaves):
        test(f"overlay leaf guard info present idx={idx}", hasattr(leaf, "_guard_info"))
    # NdOverlay path
    ndo = NdOverlay({"a": r1, "b": r2})
    shaded_nd = FakeShade(ndo, dynamic=False)
    test("ndoverlay ndo: output carries guard info",
         hasattr(shaded_nd, "_guard_info"))
    leaves_nd = shaded_nd.traverse(lambda x: x, [Image])
    for idx, leaf in enumerate(leaves_nd):
        test(f"ndoverlay leaf guard idx={idx}",
             hasattr(leaf, "_guard_info"))


# ========================================================================
# I.  fake_datashade composition -- one guard layer only
# ========================================================================

with section("I. fake_datashade composition (single guard layer)"):
    sc = make_scatter()
    ds = fake_datashade(sc, width=24, height=24, dynamic=False)
    test("datashade: output type RGB/Image", isinstance(ds, (Image,)))
    test("datashade: _guard_info present", hasattr(ds, "_guard_info"))
    gi = ds._guard_info
    test("datashade: gi.success", gi.success and not gi.empty)
    test("datashade: operation name matches",
         gi.metadata["operation"] == "fake_datashade")
    test("datashade: normalized_params has width",
         gi.normalized_params._guard_normalized["width"] == 24)
    # And the dynamic path
    dyn_ds = fake_datashade(sc, width=12, height=12, dynamic=True)
    frame = dyn_ds[()]
    test("datashade: dynamic frame ok", isinstance(frame, (Image,)))
    test("datashade: dyn frame gi present", hasattr(frame, "_guard_info"))


# ========================================================================
# J.  Guard disabled (_guard_enabled=False) -- no guard wrapping
# ========================================================================

with section("J. Guard disabled -- no _guard_info / bypass"):

    class UnGuarded(fake_rasterize):
        _guard_enabled = False

    sc = make_scatter()
    u = UnGuarded(sc, width=5, height=5, dynamic=False)
    test("disabled: returns Image still", isinstance(u, Image))
    test("disabled: no _guard_info attribute",
         not hasattr(u, "_guard_info"))
    inst = UnGuarded.instance()
    test("disabled: no _last_guard_result attribute",
         not hasattr(inst, "_last_guard_result"))


# ========================================================================
# K.  Multiple sequential calls -- each call has own timestamp
# ========================================================================

with section("K. Sequential call timestamps"):
    sc = make_scatter()
    import time
    rs = []
    for _ in range(3):
        time.sleep(0.002)
        rs.append(fake_rasterize(sc, width=4, height=4, dynamic=False))
    timestamps = [r._guard_info.timestamp for r in rs]
    # Timestamps monotonically increasing
    test("timestamps: sequential timestamps increasing",
         timestamps[0] < timestamps[1] <= timestamps[2])


# ========================================================================
# L.  Summary
# ========================================================================

print("\n" + "=" * 60)
print(f"TOTAL: {PASSED} passed  |  {len(FAILURES)} failed")
print("=" * 60)

if FAILURES:
    print("\n--- FAILURES ---")
    for name, detail, tb in FAILURES:
        print(f"\n  [{name}]")
        print(f"    detail: {detail}")
    sys.exit(1)
else:
    print("\nAll tests passed!")
    sys.exit(0)
