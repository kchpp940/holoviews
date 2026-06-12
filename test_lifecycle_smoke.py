"""Basic smoke tests to verify lifecycle changes don't break core functionality"""
import holoviews as hv
import numpy as np
import traceback

passed = 0
failed = 0

def run_test(name, fn):
    global passed, failed
    try:
        result = fn()
        if result is None or result:
            passed += 1
            print(f"✓ {name}")
        else:
            failed += 1
            print(f"✗ {name} - returned False")
    except Exception as e:
        failed += 1
        print(f"✗ {name} - {type(e).__name__}: {e}")
        traceback.print_exc()


def test_bokeh_basic_curve():
    hv.extension("bokeh", logo=False)
    hv.output(backend="bokeh")
    curve = hv.Curve([1, 2, 3])
    renderer = hv.renderer("bokeh")
    plot = renderer.get_plot(curve)
    fig = renderer.get_plot_state(plot)
    assert fig is not None
    return True


def test_bokeh_overlay():
    hv.extension("bokeh", logo=False)
    hv.output(backend="bokeh")
    curve1 = hv.Curve([1, 2, 3], label="Curve 1")
    curve2 = hv.Curve([3, 2, 1], label="Curve 2")
    overlay = curve1 * curve2
    renderer = hv.renderer("bokeh")
    plot = renderer.get_plot(overlay)
    fig = renderer.get_plot_state(plot)
    assert fig is not None
    return True


def test_bokeh_layout():
    hv.extension("bokeh", logo=False)
    hv.output(backend="bokeh")
    curve1 = hv.Curve([1, 2, 3])
    curve2 = hv.Curve([3, 2, 1])
    layout = curve1 + curve2
    renderer = hv.renderer("bokeh")
    plot = renderer.get_plot(layout)
    fig = renderer.get_plot_state(plot)
    assert fig is not None
    return True


def test_bokeh_grid():
    hv.extension("bokeh", logo=False)
    hv.output(backend="bokeh")
    data = {i: hv.Curve([i, i+1, i+2]) for i in range(4)}
    grid = hv.GridSpace(data, kdims=["x"])
    renderer = hv.renderer("bokeh")
    plot = renderer.get_plot(grid)
    fig = renderer.get_plot_state(plot)
    assert fig is not None
    return True


def test_mpl_basic_curve():
    hv.extension("matplotlib", logo=False)
    hv.output(backend="matplotlib")
    curve = hv.Curve([1, 2, 3])
    renderer = hv.renderer("matplotlib")
    plot = renderer.get_plot(curve)
    fig = renderer.get_plot_state(plot)
    assert fig is not None
    return True


def test_mpl_overlay():
    hv.extension("matplotlib", logo=False)
    hv.output(backend="matplotlib")
    curve1 = hv.Curve([1, 2, 3], label="Curve 1")
    curve2 = hv.Curve([3, 2, 1], label="Curve 2")
    overlay = curve1 * curve2
    renderer = hv.renderer("matplotlib")
    plot = renderer.get_plot(overlay)
    fig = renderer.get_plot_state(plot)
    assert fig is not None
    return True


def test_mpl_layout():
    hv.extension("matplotlib", logo=False)
    hv.output(backend="matplotlib")
    curve1 = hv.Curve([1, 2, 3])
    curve2 = hv.Curve([3, 2, 1])
    layout = curve1 + curve2
    renderer = hv.renderer("matplotlib")
    plot = renderer.get_plot(layout)
    fig = renderer.get_plot_state(plot)
    assert fig is not None
    return True


def test_mpl_grid():
    hv.extension("matplotlib", logo=False)
    hv.output(backend="matplotlib")
    data = {i: hv.Curve([i, i+1, i+2]) for i in range(4)}
    grid = hv.GridSpace(data, kdims=["x"])
    renderer = hv.renderer("matplotlib")
    plot = renderer.get_plot(grid)
    fig = renderer.get_plot_state(plot)
    assert fig is not None
    return True


def test_plotly_basic_curve():
    hv.extension("plotly", logo=False)
    hv.output(backend="plotly")
    curve = hv.Curve([1, 2, 3])
    renderer = hv.renderer("plotly")
    plot = renderer.get_plot(curve)
    fig = renderer.get_plot_state(plot)
    assert fig is not None
    return True


def test_plotly_overlay():
    hv.extension("plotly", logo=False)
    hv.output(backend="plotly")
    curve1 = hv.Curve([1, 2, 3], label="Curve 1")
    curve2 = hv.Curve([3, 2, 1], label="Curve 2")
    overlay = curve1 * curve2
    renderer = hv.renderer("plotly")
    plot = renderer.get_plot(overlay)
    fig = renderer.get_plot_state(plot)
    assert fig is not None
    return True


def test_plotly_layout():
    hv.extension("plotly", logo=False)
    hv.output(backend="plotly")
    curve1 = hv.Curve([1, 2, 3])
    curve2 = hv.Curve([3, 2, 1])
    layout = curve1 + curve2
    renderer = hv.renderer("plotly")
    plot = renderer.get_plot(layout)
    fig = renderer.get_plot_state(plot)
    assert fig is not None
    return True


def test_plotly_grid():
    hv.extension("plotly", logo=False)
    hv.output(backend="plotly")
    data = {i: hv.Curve([i, i+1, i+2]) for i in range(4)}
    grid = hv.GridSpace(data, kdims=["x"])
    renderer = hv.renderer("plotly")
    plot = renderer.get_plot(grid)
    fig = renderer.get_plot_state(plot)
    assert fig is not None
    return True


def test_lifecycle_hooks_registration():
    """Test that lifecycle hooks can be registered and are triggered"""
    from holoviews.plotting.lifecycle import LifecycleHook, LifecyclePhase

    class TestHook(LifecycleHook):
        def __init__(self):
            super().__init__()
            self.phases = []

        def should_run(self, phase, when, ctx):
            return True

        def run(self, phase, when, ctx):
            self.phases.append((phase.name, when))
            return ctx

    hv.extension("bokeh", logo=False)
    hv.output(backend="bokeh")
    hook = TestHook()
    renderer = hv.renderer("bokeh")
    renderer.lifecycle_hooks = [hook]

    try:
        curve = hv.Curve([1, 2, 3])
        plot = renderer.get_plot(curve)
        fig = renderer.get_plot_state(plot)

        assert len(hook.phases) > 0, "No lifecycle phases were triggered"
        phase_names = [p[0] for p in hook.phases]
        assert "PRE_INIT" in phase_names
        assert "POST_INIT" in phase_names
        return True
    finally:
        renderer.lifecycle_hooks = []


print("=" * 70)
print("Running HoloViews lifecycle smoke tests")
print("=" * 70)

run_test("Bokeh: Basic Curve", test_bokeh_basic_curve)
run_test("Bokeh: Overlay", test_bokeh_overlay)
run_test("Bokeh: Layout", test_bokeh_layout)
run_test("Bokeh: GridSpace", test_bokeh_grid)
run_test("MPL: Basic Curve", test_mpl_basic_curve)
run_test("MPL: Overlay", test_mpl_overlay)
run_test("MPL: Layout", test_mpl_layout)
run_test("MPL: GridSpace", test_mpl_grid)
run_test("Plotly: Basic Curve", test_plotly_basic_curve)
run_test("Plotly: Overlay", test_plotly_overlay)
run_test("Plotly: Layout", test_plotly_layout)
run_test("Plotly: GridSpace", test_plotly_grid)
run_test("Lifecycle hooks registration and triggering", test_lifecycle_hooks_registration)

print("=" * 70)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 70)

import sys
sys.exit(0 if failed == 0 else 1)
