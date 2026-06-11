import sys
import warnings
import holoviews as hv
from holoviews.core.runtime import DynamicMapContext
from holoviews.plotting.util import _last_frame, initialize_dynamic, get_plot_frame
from holoviews.util.warnings import HoloviewsDeprecationWarning
from holoviews import streams

passed = 0
failed = 0

def test(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f'  PASS {name}')
    except Exception as e:
        failed += 1
        print(f'  FAIL {name}')
        import traceback
        traceback.print_exc()
        print()

def data_len(el):
    if hasattr(el.data, '__len__'):
        try:
            if hasattr(el.data, 'values'):
                return max(len(v) for v in el.data.values())
            return len(el.data)
        except Exception:
            return len(el)
    return len(el)

print('=== 1. Deprecation warnings: INTERNAL calls do NOT trigger warnings ===')
def test_no_internal_warnings():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        dmap = hv.DynamicMap(lambda i: hv.Curve(range(i+1)), kdims=['i'])
        dmap.kdims[0].range = (0, 10)
        # 内部调用：__getitem__, initialize_dynamic, get_plot_frame 等
        curve = dmap[5]
        initialize_dynamic(dmap)
        get_plot_frame(dmap, {'i': 7})
        frame = _last_frame(dmap)
        # 不应该有 HoloviewsDeprecationWarning
        dep_warns = [x for x in w if issubclass(x.category, HoloviewsDeprecationWarning)]
        assert len(dep_warns) == 0, f"Unexpected internal deprecation warnings: {[str(x.message) for x in dep_warns]}"
test('Internal calls do not trigger deprecation warnings', test_no_internal_warnings)

print()
print('=== 2. Deprecation warnings: EXTERNAL calls DO trigger warnings ===')
def test_external_warnings():
    dmap = hv.DynamicMap(lambda i: hv.Curve(range(i+1)), kdims=['i'])
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _ = dmap._current_key
        _ = dmap._posarg_keys
        _ = dmap._stream_parameters()
        dep_warns = [x for x in w if issubclass(x.category, HoloviewsDeprecationWarning)]
        assert len(dep_warns) >= 3, f"Expected >= 3 deprecation warnings, got {len(dep_warns)}: {[str(x.message) for x in dep_warns]}"
test('External access to _current_key/_posarg_keys etc triggers warnings', test_external_warnings)

print()
print('=== 3. plotting/util._last_frame helper works for both HoloMap and DynamicMap ===')
def test_last_frame_helper():
    # DynamicMap
    dmap = hv.DynamicMap(lambda i: hv.Curve(range(i+1)), kdims=['i'])
    dmap[3]
    dmap[7]
    lf = _last_frame(dmap)
    assert data_len(lf) == 8
    # HoloMap
    hmap = hv.HoloMap({i: hv.Curve(range(i+1)) for i in range(5)}, kdims=['i'])
    lf2 = _last_frame(hmap)
    assert data_len(lf2) == 5
    # None DynamicMap
    dmap2 = hv.DynamicMap(lambda i: hv.Curve(range(i+1)), kdims=['i'])
    lf3 = _last_frame(dmap2)
    assert lf3 is None
test('_last_frame helper works correctly', test_last_frame_helper)

print()
print('=== 4. Spaces.py L1545 uses context.initial_key() (not _initial_key wrapper) ===')
def test_collate_uses_context():
    dmap = hv.DynamicMap(lambda i: hv.Curve(range(i+1)), kdims=['i'])
    dmap.kdims[0].range = (0, 3)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        # collate 内部应直接走 context._context.initial_key()
        result = dmap.collate()
        dep_warns = [x for x in w if issubclass(x.category, HoloviewsDeprecationWarning)]
        assert len(dep_warns) == 0, f"collate should not trigger deprecation warnings, got: {[str(x.message) for x in dep_warns]}"
test('collate() uses context directly', test_collate_uses_context)

print()
print('=== 5. plotting/plot.py uses _last_frame helper ===')
def test_plot_uses_last_frame():
    from holoviews.plotting.plot import DimensionedPlot
    # Verify _last_frame is imported
    from holoviews.plotting.plot import _last_frame as plot_lf
    assert callable(plot_lf)
    dmap = hv.DynamicMap(lambda i: hv.Curve(range(i+1)), kdims=['i'])
    dmap[5]
    lf = plot_lf(dmap)
    assert data_len(lf) == 6
test('plot.py _last_frame helper works', test_plot_uses_last_frame)

print()
print('=== 6. Context stable APIs still all work ===')
def test_context_apis():
    dmap = hv.DynamicMap(lambda i: hv.Curve(range(i+1)), kdims=['i'])
    dmap.kdims[0].range = (0, 10)
    # get_frame
    frame = dmap.context.get_frame({'i': 4})
    assert data_len(frame) == 5
    # resolve_posarg_key
    assert dmap.context.resolve_posarg_key({'i': 7}) == (7,)
    # initialize
    dmap2 = hv.DynamicMap(lambda i: hv.Curve(range(i+1)), kdims=['i'])
    dmap2.kdims[0].range = (0, 5)
    assert len(dmap2.data) == 0
    dmap2.context.initialize()
    assert len(dmap2.data) == 1
    # handle_event + event_reason
    counter = streams.Counter()
    dmap3 = hv.DynamicMap(lambda counter: hv.Curve([counter]), kdims=[], streams=[counter])
    dmap3.context.handle_event(counter=5)
    assert dmap3.context.event_reason == 'manual_event'
    # stream_parameters
    params = dmap3.context.stream_parameters()
    assert 'counter' in params
    # initial_key / validate_key
    ikey = dmap.context.initial_key()
    assert ikey == (0,)
    dmap.context.validate_key((3,))
    # execute_callback / cache_value
    val = dmap.context.execute_callback(6)
    assert data_len(val) == 7
    dmap.context.cache_value((6,), val)
    assert (6,) in dmap.data
    # last_key / last_frame
    assert dmap.context.last_key == (6,)
    lf = dmap.context.last_frame
    assert data_len(lf) == 7
    # set_event_reason / clear
    dmap.context.set_event_reason('periodic', count=42)
    assert dmap.context.event_reason == 'periodic'
    assert dmap.context.event_metadata == {'count': 42}
    dmap.context.clear_event_reason()
    assert dmap.context.event_reason is None
    assert dmap.context.event_metadata == {}
test('All context stable APIs work correctly', test_context_apis)

print()
print('=== 7. Backward compat: old APIs still work but emit warnings ===')
def test_backward_compat_warns():
    dmap = hv.DynamicMap(lambda i: hv.Curve(range(i+1)), kdims=['i'])
    dmap.kdims[0].range = (0, 10)
    # All deprecated APIs should still function
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dmap[2]
        ck = dmap._current_key
        assert ck == 2
        pk = dmap._posarg_keys
        assert pk is not None
        sp = dmap._stream_parameters()
        assert isinstance(sp, list)
        ik = dmap._initial_key()
        assert isinstance(ik, tuple)
        dmap._validate_key((3,))
        cb = dmap._execute_callback(4)
        assert data_len(cb) == 5
        # event() is public API, should still work
        counter = streams.Counter()
        dmap2 = hv.DynamicMap(lambda counter: hv.Curve([counter]), kdims=[], streams=[counter])
        dmap2.event(counter=5)
        assert dmap2.context.event_reason == 'manual_event'
test('Deprecated APIs still functional (backward compat)', test_backward_compat_warns)

print()
print(f'====================')
print(f'Total: {passed + failed}  Passed: {passed}  Failed: {failed}')
if failed > 0:
    sys.exit(1)
