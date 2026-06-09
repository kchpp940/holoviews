"""Verify the _hv_id identity column fix for Bokeh linked selections."""
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import holoviews as hv
from holoviews.selection import link_selections

hv.extension("bokeh")

def test_identity_columns_from_dataframe_index():
    """Test that _get_identity_columns returns DataFrame index names."""
    print("Test 1: _get_identity_columns from pandas DataFrame index")
    df = pd.DataFrame({"x": [1, 2, 3], "y": [10, 20, 30]}, index=pd.Index(["a", "b", "c"], name="idx"))
    table = hv.Table(df)
    cols = table._get_identity_columns()
    assert cols == ["idx"], f"Expected ['idx'], got {cols}"
    print(f"  PASS: identity columns = {cols}")

def test_identity_values_from_dataframe_index():
    """Test that _get_identity_values returns correct DataFrame index values."""
    print("Test 2: _get_identity_values from pandas DataFrame index")
    df = pd.DataFrame({"x": [1, 2, 3], "y": [10, 20, 30]}, index=pd.Index(["a", "b", "c"], name="idx"))
    table = hv.Table(df)
    vals = table._get_identity_values()
    assert vals == ["a", "b", "c"], f"Expected ['a', 'b', 'c'], got {vals}"
    print(f"  PASS: identity values = {vals}")

def test_index_selection_with_identity_values():
    """Test _get_index_selection with identity values (not row numbers)."""
    print("Test 3: _get_index_selection with identity values")
    df = pd.DataFrame({"x": [1, 2, 3, 4], "y": [10, 20, 30, 40]}, index=pd.Index(["a", "b", "c", "d"], name="idx"))
    table = hv.Table(df)
    expr, _, _ = table._get_index_selection(["a", "c"], index_cols=None)
    assert expr is not None, "Expression should not be None"
    mask = expr.apply(table.dataset, expanded=True, flat=True)
    selected = list(np.where(mask)[0])
    assert selected == [0, 2], f"Expected [0, 2], got {selected}"
    print(f"  PASS: selected rows = {selected}")

def test_index_selection_with_row_numbers():
    """Test _get_index_selection still works with legacy row numbers."""
    print("Test 4: _get_index_selection with legacy row numbers")
    df = pd.DataFrame({"x": [1, 2, 3, 4], "y": [10, 20, 30, 40]}, index=pd.Index(["a", "b", "c", "d"], name="idx"))
    table = hv.Table(df)
    expr, _, _ = table._get_index_selection([0, 2], index_cols=None)
    assert expr is not None, "Expression should not be None"
    mask = expr.apply(table.dataset, expanded=True, flat=True)
    selected = list(np.where(mask)[0])
    assert selected == [0, 2], f"Expected [0, 2], got {selected}"
    print(f"  PASS: selected rows = {selected}")

def test_duplicate_kdims_with_dataframe_index():
    """Test selection with duplicate kdims but unique DataFrame index."""
    print("Test 5: Duplicate kdims with unique DataFrame index")
    df = pd.DataFrame(
        {"cat": ["a", "a", "b", "b"], "x": [1, 1, 1, 2], "value": [10, 20, 30, 40]},
        index=pd.Index([100, 101, 102, 103], name="row_id")
    )
    table = hv.Table(df, kdims=["cat", "x"], vdims=["value"])
    expr, _, _ = table._get_index_selection([100], index_cols=None)
    assert expr is not None, "Expression should not be None"
    mask = expr.apply(table.dataset, expanded=True, flat=True)
    selected = list(np.where(mask)[0])
    assert selected == [0], f"Expected only row 0 (row_id=100), got {selected}"
    print(f"  PASS: selected rows = {selected} (duplicate cat/x but unique row_id)")

def test_selection_transfer_across_different_order():
    """Test that identity-based selection transfers between differently-ordered datasets."""
    print("Test 6: Selection transfers across differently-ordered datasets")
    df1 = pd.DataFrame(
        {"value": [10, 20, 30, 40]},
        index=pd.Index(["a", "b", "c", "d"], name="id")
    )
    df2 = pd.DataFrame(
        {"value": [40, 30, 20, 10]},
        index=pd.Index(["d", "c", "b", "a"], name="id")
    )
    t1 = hv.Table(df1)
    expr, _, _ = t1._get_index_selection(["a", "c"], index_cols=None)

    t2 = hv.Table(df2)
    mask = expr.apply(t2.dataset, expanded=True, flat=True)
    selected = list(np.where(mask)[0])
    assert selected == [1, 3], f"Expected [1, 3] (ids 'c' and 'a' in df2), got {selected}"
    print(f"  PASS: selected rows in reversed dataset = {selected}")

def test_bars_selection_with_identity_values():
    """Test SelectionBarsExpr handles identity values correctly."""
    print("Test 7: SelectionBarsExpr with identity values")
    df = pd.DataFrame(
        {"cat": ["a", "a", "b", "b"], "x": [1, 2, 1, 2], "value": [10, 20, 30, 40]},
        index=pd.Index([10, 20, 30, 40], name="bar_id")
    )
    bars = hv.Bars(df, kdims=["cat", "x"], vdims=["value"])
    expr, _, _ = bars._get_index_selection([10, 40], index_cols=None)
    assert expr is not None, "Expression should not be None"
    mask = expr.apply(bars.dataset, expanded=True, flat=True)
    selected = list(np.where(mask)[0])
    assert selected == [0, 3], f"Expected [0, 3], got {selected}"
    print(f"  PASS: selected bars = {selected}")

def test_multiindex_dataframe():
    """Test selection with pandas MultiIndex DataFrame."""
    print("Test 8: MultiIndex DataFrame identity")
    df = pd.DataFrame(
        {"value": [10, 20, 30, 40]},
        index=pd.MultiIndex.from_tuples([("a", 1), ("a", 2), ("b", 1), ("b", 2)], names=["cat", "x"])
    )
    table = hv.Table(df)
    cols = table._get_identity_columns()
    assert cols == ["cat", "x"], f"Expected ['cat', 'x'], got {cols}"
    vals = table._get_identity_values()
    assert vals == [("a", 1), ("a", 2), ("b", 1), ("b", 2)], f"Got {vals}"
    expr, _, _ = table._get_index_selection([("a", 1), ("b", 2)], index_cols=None)
    assert expr is not None, "Expression should not be None"
    mask = expr.apply(table.dataset, expanded=True, flat=True)
    selected = list(np.where(mask)[0])
    assert selected == [0, 3], f"Expected [0, 3], got {selected}"
    print(f"  PASS: multi-index selection rows = {selected}")

def test_postprocess_data_injects_hv_id():
    """Test that BokehPlot._postprocess_data injects _hv_id."""
    print("Test 9: BokehPlot._postprocess_data injects _hv_id")
    from holoviews.plotting.bokeh.plot import BokehPlot

    element = hv.Table({"x": [1, 2, 3]}, kdims=["x"])

    class FakePlot:
        current_frame = element
        def _get_identity_values(self, el, n):
            return list(range(n))
        def param_warning(self, msg): pass

    BokehPlot._postprocess_data.__globals__["cftime_types"] = ()
    BokehPlot._postprocess_data.__globals__["_STANDARD_CALENDARS"] = set()
    BokehPlot._postprocess_data.__globals__["cftime_to_timestamp"] = lambda x, y: x
    BokehPlot._postprocess_data.__globals__["decode_bytes"] = lambda x: x

    data = {"x": [1, 2, 3]}
    result = BokehPlot._postprocess_data(FakePlot(), data)
    assert "_hv_id" in result, f"_hv_id should be in result keys. Got: {list(result.keys())}"
    assert list(result["_hv_id"]) == [0, 1, 2], f"_hv_id values wrong: {result['_hv_id']}"
    print(f"  PASS: _hv_id injected = {list(result['_hv_id'])}")

def test_postprocess_data_injects_hv_id_from_dataframe_index():
    """Test _postprocess_data uses DataFrame index for _hv_id."""
    print("Test 10: _postprocess_data uses DataFrame index for _hv_id")
    from holoviews.plotting.bokeh.plot import BokehPlot

    df = pd.DataFrame({"x": [1, 2, 3]}, index=pd.Index(["p", "q", "r"], name="myid"))
    element = hv.Table(df, kdims=["x"])

    class FakePlot:
        current_frame = element
        def _get_identity_values(self, el, n):
            try:
                import pandas as pd
                if isinstance(el.data, pd.DataFrame):
                    idx = el.data.index
                    if idx.nlevels == 1:
                        return list(idx.values)
                    else:
                        return [tuple(v) for v in idx.values]
            except Exception:
                pass
            return list(range(n))
        def param_warning(self, msg): pass

    BokehPlot._postprocess_data.__globals__["cftime_types"] = ()
    BokehPlot._postprocess_data.__globals__["_STANDARD_CALENDARS"] = set()
    BokehPlot._postprocess_data.__globals__["cftime_to_timestamp"] = lambda x, y: x
    BokehPlot._postprocess_data.__globals__["decode_bytes"] = lambda x: x

    data = {"x": [1, 2, 3]}
    result = BokehPlot._postprocess_data(FakePlot(), data)
    assert "_hv_id" in result
    assert list(result["_hv_id"]) == ["p", "q", "r"], f"Got: {result['_hv_id']}"
    print(f"  PASS: _hv_id from DataFrame index = {list(result['_hv_id'])}")

if __name__ == "__main__":
    test_identity_columns_from_dataframe_index()
    test_identity_values_from_dataframe_index()
    test_index_selection_with_identity_values()
    test_index_selection_with_row_numbers()
    test_duplicate_kdims_with_dataframe_index()
    test_selection_transfer_across_different_order()
    test_bars_selection_with_identity_values()
    test_multiindex_dataframe()
    test_postprocess_data_injects_hv_id()
    test_postprocess_data_injects_hv_id_from_dataframe_index()
    print("\nAll tests passed!")
