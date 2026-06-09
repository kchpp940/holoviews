"""Verify shared helper + BokehPlot/SelectionIndexExpr all produce identical results."""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import holoviews as hv
from holoviews.element.selection import (
    _is_default_dataframe_index,
    get_identity_columns,
    get_identity_values,
)
from holoviews.selection import link_selections

hv.extension("bokeh")

def test_shared_helper_matches_selection_expr():
    """Shared get_identity_values/columns must match SelectionIndexExpr wrappers exactly."""
    print("Test 1: Shared helper == SelectionIndexExpr wrappers")
    print("=" * 70)

    cases = [
        ("Default RangeIndex", pd.DataFrame({"x": [1, 2, 3], "y": [10, 20, 30]})),
        ("Unnamed Int64Index", pd.DataFrame({"x": [1,2,3], "y": [10,20,30]}, index=pd.Index([10, 20, 30]))),
        ("Named RangeIndex non-default", pd.DataFrame({"x": [1,2,3], "y": [10,20,30]}, index=pd.RangeIndex(100, 103, name="rid"))),
        ("Filtered view", pd.DataFrame({"x": list(range(10)), "y": list(range(10))}, index=pd.RangeIndex(100, 110)).iloc[3:7]),
        ("Unnamed string Index", pd.DataFrame({"x": [1,2,3], "y": [10,20,30]}, index=pd.Index(["a", "b", "c"]))),
        ("Unnamed MultiIndex", pd.DataFrame({"x": [1,2,3], "y": [10,20,30]}, index=pd.MultiIndex.from_tuples([("a",1),("b",2),("c",3)]))),
        ("Default RangeIndex + kdims", pd.DataFrame({"cat": ["A","B","A"], "val": [10,20,30]}), ["cat"], ["val"]),
    ]

    all_pass = True
    for case in cases:
        if len(case) == 4:
            name, df, kdims, vdims = case
        elif len(case) == 3:
            name, df, kdims = case
            vdims = list(set(df.columns) - set(kdims))
        else:
            name, df = case
            kdims, vdims = ["x"], ["y"]

        t = hv.Table(df, kdims=kdims, vdims=vdims)

        kdim_names = [d.name for d in t.kdims]
        all_dim_names = [d.name for d in t.dimensions()]

        cols_helper = get_identity_columns(t, None, kdim_names, all_dim_names)
        cols_wrapper = t._get_identity_columns()
        vals_helper = get_identity_values(t, None)
        vals_wrapper = t._get_identity_values()

        cols_ok = cols_helper == cols_wrapper
        vals_ok = list(vals_helper) == list(vals_wrapper)
        status = "PASS" if (cols_ok and vals_ok) else "FAIL"
        print(f"  [{status}] {name}")
        if not cols_ok:
            print(f"    cols helper:   {cols_helper}")
            print(f"    cols wrapper:  {cols_wrapper}")
            all_pass = False
        if not vals_ok:
            print(f"    vals helper[:3]: {vals_helper[:3]}")
            print(f"    vals wrapper[:3]: {vals_wrapper[:3]}")
            all_pass = False

    assert all_pass, "Some cases diverged between shared helper and wrapper"
    print()
    print("PASS: Shared helper and SelectionIndexExpr wrappers are identical")


def test_is_default_dataframe_index():
    """Test _is_default_dataframe_index helper for all index types."""
    print()
    print("Test 2: _is_default_dataframe_index helper")
    print("=" * 70)
    n = 5

    cases = [
        (pd.RangeIndex(0, n, 1), True, "default RangeIndex(0, n, 1)"),
        (pd.RangeIndex(0, n, 2), False, "RangeIndex(0, n, 2) step != 1"),
        (pd.RangeIndex(100, 100 + n, 1), False, "RangeIndex(100, ...) start != 0"),
        (pd.Index(list(range(n))), True, "Int64Index([0..n-1])"),
        (pd.Index([10, 20, 30, 40, 50]), False, "Int64Index([10,20,...])"),
        (pd.Index(["a", "b", "c", "d", "e"]), False, "string Index"),
        (pd.MultiIndex.from_tuples([(i, i*10) for i in range(n)]), False, "MultiIndex"),
    ]

    for idx, expected, name in cases:
        got = _is_default_dataframe_index(idx, n)
        status = "PASS" if got == expected else "FAIL"
        print(f"  [{status}] {name}: expected {expected}, got {got}")
        assert got == expected, f"Failed: {name}"

    print()
    print("PASS: _is_default_dataframe_index correct for all index types")


def test_bokehplot_and_selection_expr_agree():
    """BokehPlot._get_identity_values and SelectionIndexExpr must agree."""
    print()
    print("Test 3: BokehPlot._get_identity_values == SelectionIndexExpr._get_identity_values")
    print("=" * 70)

    from holoviews.plotting.bokeh.plot import BokehPlot

    cases = [
        ("Default RangeIndex", pd.DataFrame({"x": [1, 2, 3, 4], "y": [10, 20, 30, 40]})),
        ("Unnamed non-default", pd.DataFrame({"x": [1,2,3,4], "y": [10,20,30,40]}, index=pd.Index([10, 20, 30, 40]))),
        ("Filtered view", pd.DataFrame({"x": list(range(10)), "y": list(range(10))}, index=pd.RangeIndex(100, 110)).iloc[2:8]),
    ]

    all_pass = True
    for name, df in cases:
        element = hv.Table(df, kdims=["x"], vdims=["y"])
        nrows = len(df)

        # BokehPlot version (no explicit index_cols via streams)
        class FakeStreams:
            streams = []
        fake_plot = FakeStreams()
        fake_plot.__class__ = BokehPlot
        bokeh_vals = BokehPlot._get_identity_values(fake_plot, element, nrows)

        # SelectionIndexExpr version (no explicit index_cols)
        expr_vals = element._get_identity_values()

        ok = list(bokeh_vals) == list(expr_vals)
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if not ok:
            print(f"    bokeh: {bokeh_vals}")
            print(f"    expr:   {expr_vals}")
            all_pass = False

    assert all_pass, "BokehPlot and SelectionIndexExpr diverged"
    print()
    print("PASS: BokehPlot and SelectionIndexExpr produce identical identity values")


def test_explicit_index_cols_priority():
    """Explicit index_cols must override DataFrame index in all entry points."""
    print()
    print("Test 4: Explicit index_cols priority > DataFrame index")
    print("=" * 70)

    df = pd.DataFrame(
        {"user_id": [101, 102, 103, 101], "session": [1, 1, 1, 2], "score": [85, 90, 78, 92]},
        index=pd.Index([1000, 1001, 1002, 1003], name="df_row_id"),
    )
    t = hv.Table(df, kdims=["user_id", "session"], vdims=["score"])
    ic = ["user_id", "session"]

    # Shared helper
    cols_helper = get_identity_columns(t, ic, [d.name for d in t.kdims], [d.name for d in t.dimensions()])
    vals_helper = get_identity_values(t, ic)
    # Wrapper
    cols_wrapper = t._get_identity_columns(ic)
    vals_wrapper = t._get_identity_values(ic)

    print(f"  index_cols={ic}")
    print(f"  DataFrame index: {list(df.index)} (name='df_row_id')")
    print(f"  cols from helper:  {cols_helper}")
    print(f"  cols from wrapper: {cols_wrapper}")
    print(f"  vals from helper[:3]:  {vals_helper[:3]}")
    print(f"  vals from wrapper[:3]: {vals_wrapper[:3]}")

    assert cols_helper == cols_wrapper == ["user_id", "session"], "Column mismatch"
    assert vals_helper == vals_wrapper, "Value mismatch"
    assert vals_helper[:2] == [(101, 1), (102, 1)], f"Unexpected values: {vals_helper[:2]}"

    # Now via BokehPlot streams
    from holoviews.plotting.bokeh.plot import BokehPlot

    class FakeStream:
        _index_cols = ic
    class FakePlot:
        streams = [FakeStream()]
        def param_warning(self, msg): pass
    BokehPlot._get_identity_values.__globals__["get_identity_values"] = get_identity_values

    bokeh_vals = BokehPlot._get_identity_values(FakePlot(), t, len(df))
    print(f"  bokeh (via streams._index_cols)[:3]: {bokeh_vals[:3]}")
    assert list(bokeh_vals) == list(vals_helper), "BokehPlot via streams diverges"

    print()
    print("PASS: Explicit index_cols takes priority at all entry points")


def test_end_to_end_cds_and_selection():
    """End-to-end: CDS _hv_id and cross-element selection expression match."""
    print()
    print("Test 5: End-to-end CDS _hv_id + cross-element selection")
    print("=" * 70)

    df_full = pd.DataFrame(
        {"x": list(range(10)), "y": list(range(10))},
        index=pd.RangeIndex(100, 110),  # unnamed non-default
    )
    df_sub = df_full.iloc[::2].copy()  # 100, 102, 104, 106, 108

    points = hv.Points(df_full, kdims=["x", "y"]).opts(tools=["tap"])
    table = hv.Table(df_sub, kdims=["x"], vdims=["y"])
    ls = link_selections.instance()
    layout = ls(points + table)

    from bokeh.models import ColumnDataSource
    plot = hv.render(layout)
    sources = [m for m in plot.select({"type": ColumnDataSource}) if "_hv_id" in m.data]

    print(f"  CDS _hv_id values:")
    for i, s in enumerate(sources):
        ids = list(s.data["_hv_id"])
        print(f"    CDS {i}: {ids}")

    # All CDSs for their own element should match get_identity_values
    expected_full = get_identity_values(hv.Table(df_full, kdims=["x"], vdims=["y"]))
    expected_sub = get_identity_values(hv.Table(df_sub, kdims=["x"], vdims=["y"]))
    all_ids = [list(s.data["_hv_id"]) for s in sources]
    for ids in all_ids:
        assert ids == expected_full or ids == expected_sub, (
            f"CDS ids {ids} don't match expected {expected_full} or {expected_sub}"
        )
    print(f"  All CDS _hv_id values match shared helper output")

    # Now test cross-element selection expression
    t_full = hv.Table(df_full, kdims=["x"], vdims=["y"])
    t_sub = hv.Table(df_sub, kdims=["x"], vdims=["y"])

    # Select rows 0 and 5 in full table → identity 100 and 105
    expr, _, _ = t_full._get_index_selection([0, 5], index_cols=None)
    mask_full = expr.apply(t_full.dataset, expanded=True, flat=True)
    mask_sub = expr.apply(t_sub.dataset, expanded=True, flat=True)
    sel_full = list(np.where(mask_full)[0])
    sel_sub = list(np.where(mask_sub)[0])
    full_ids = {df_full.index[i] for i in sel_full}
    sub_ids = {df_sub.index[i] for i in sel_sub}

    print(f"  Select rows [0, 5] in full → identities {full_ids}")
    print(f"    Matched in subset: rows {sel_sub} → identities {sub_ids}")
    assert full_ids == {100, 105}, f"Full ids mismatch: {full_ids}"
    assert sub_ids == {100}, f"Sub ids mismatch (only 100 in sub): {sub_ids}"

    print()
    print("PASS: End-to-end CDS and cross-element selection consistent")


if __name__ == "__main__":
    test_shared_helper_matches_selection_expr()
    test_is_default_dataframe_index()
    test_bokehplot_and_selection_expr_agree()
    test_explicit_index_cols_priority()
    test_end_to_end_cds_and_selection()
    print()
    print("=" * 70)
    print("ALL TESTS PASSED — shared identity helper is used consistently")
    print("=" * 70)
