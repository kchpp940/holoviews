"""Verify new design: Selection1D index keeps row numbers, identity mapping happens internally."""
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import holoviews as hv
from holoviews.selection import link_selections

hv.extension("bokeh")


def test_row_numbers_preserved_in_selection1d_stream():
    """Selection1D stream's index parameter should be row numbers, not identity values."""
    print("Test 1: Selection1D index preserves row number semantics")
    print("=" * 70)

    from holoviews.streams import Selection1D

    df = pd.DataFrame(
        {"x": [1, 2, 3, 4, 5], "y": [10, 20, 30, 40, 50]},
        index=pd.Index(["r100", "r101", "r102", "r103", "r104"], name="uid"),
    )
    points = hv.Points(df, kdims=["x", "y"])

    sel_stream = Selection1D(source=points)
    print(f"Initial Selection1D index: {sel_stream.index}")

    sel_stream.update(index=[0, 2, 4])
    print(f"After update(index=[0, 2, 4]): index = {sel_stream.index}")
    assert sel_stream.index == [0, 2, 4], (
        f"Selection1D.index should be row numbers [0,2,4], got {sel_stream.index}"
    )

    print()
    print("PASS: Selection1D.index retains row number semantics")


def test_selection_expr_built_from_row_numbers_maps_by_identity():
    """Selection expression built from row numbers should select by identity, not row position."""
    print()
    print("Test 2: Selection expr from row numbers → identity-based cross-element mapping")
    print("=" * 70)

    df_orig = pd.DataFrame(
        {"x": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], "y": list(range(10))},
        index=pd.Index(
            ["row_a", "row_b", "row_c", "row_d", "row_e", "row_f", "row_g", "row_h", "row_i", "row_j"],
            name="uid",
        ),
    )

    df_reordered = df_orig.iloc[::-1].reset_index(drop=False).set_index("uid")

    print(f"Original DataFrame index: {df_orig.index.tolist()}")
    print(f"Reversed DataFrame index: {df_reordered.index.tolist()}")
    print()

    t_orig = hv.Table(df_orig, kdims=["x"], vdims=["y"])
    t_rev = hv.Table(df_reordered, kdims=["x"], vdims=["y"])

    row_numbers_orig = [0, 2, 5]
    print(f"Selected row numbers on ORIGINAL table: {row_numbers_orig}")
    expected_ids = [df_orig.index[i] for i in row_numbers_orig]
    print(f"  → Expected identities: {expected_ids}")

    expr, _, _ = t_orig._get_index_selection(row_numbers_orig, index_cols=None)
    print(f"Generated selection expression: {expr}")

    mask_orig = expr.apply(t_orig.dataset, expanded=True, flat=True)
    mask_rev = expr.apply(t_rev.dataset, expanded=True, flat=True)

    sel_orig = list(np.where(mask_orig)[0])
    sel_rev = list(np.where(mask_rev)[0])

    print(f"  → Rows selected on ORIGINAL table: {sel_orig}")
    print(f"  → Rows selected on REVERSED table: {sel_rev}")
    print(f"    Original identities: {[df_orig.index[i] for i in sel_orig]}")
    print(f"    Reversed identities: {[df_reordered.index[i] for i in sel_rev]}")

    orig_ids = set(df_orig.index[i] for i in sel_orig)
    rev_ids = set(df_reordered.index[i] for i in sel_rev)
    expected_set = set(expected_ids)

    assert orig_ids == expected_set, f"Original identities {orig_ids} != expected {expected_set}"
    assert rev_ids == expected_set, f"Reversed identities {rev_ids} != expected {expected_set}"

    assert sel_orig != sel_rev, (
        f"Row numbers should differ between original and reversed tables, but both got {sel_orig}"
    )

    print()
    print("PASS: Selection by identity correctly maps across differently-ordered datasets")


def test_index_cols_priority_over_dataframe_index():
    """Explicit index_cols parameter should take priority over DataFrame index."""
    print()
    print("Test 3: index_cols priority > DataFrame index")
    print("=" * 70)

    df = pd.DataFrame(
        {"user_id": [101, 102, 103, 101, 102, 103], "session": [1, 1, 1, 2, 2, 2], "score": [85, 90, 78, 92, 88, 81]},
        index=pd.Index([1000, 1001, 1002, 1003, 1004, 1005], name="df_row_id"),
    )

    print("DataFrame:")
    print(df)
    print(f"  DataFrame index name: 'df_row_id', values: {df.index.tolist()}")
    print(f"  user_id+session: {(df['user_id'].astype(str) + '_' + df['session'].astype(str)).tolist()}")
    print()

    table = hv.Table(df, kdims=["user_id", "session"], vdims=["score"])

    # Without explicit index_cols → should fall back to DataFrame index
    cols_default = table._get_identity_columns(index_cols=None)
    print(f"identity columns (no index_cols): {cols_default}")
    assert cols_default == ["df_row_id"], f"Expected ['df_row_id'] (DataFrame index), got {cols_default}"

    # With explicit index_cols → should use index_cols, NOT DataFrame index
    cols_explicit = table._get_identity_columns(index_cols=["user_id", "session"])
    print(f"identity columns (index_cols=['user_id','session']): {cols_explicit}")
    assert cols_explicit == ["user_id", "session"], (
        f"Expected ['user_id','session'], got {cols_explicit}"
    )

    vals_default = table._get_identity_values(index_cols=None)
    print(f"identity values (no index_cols) [first 3]: {vals_default[:3]}")
    assert [int(v) for v in vals_default[:3]] == [1000, 1001, 1002], (
        f"Expected [1000, 1001, 1002], got {vals_default[:3]}"
    )

    vals_explicit = table._get_identity_values(index_cols=["user_id", "session"])
    print(f"identity values (index_cols=...) [first 3]: {vals_explicit[:3]}")
    assert [(int(v[0]), int(v[1])) for v in vals_explicit[:3]] == [(101, 1), (102, 1), (103, 1)], (
        f"Expected [(101,1), (102,1), (103,1)], got {vals_explicit[:3]}"
    )

    print()
    print("PASS: Explicit index_cols takes priority over DataFrame index")


def test_update_selected_with_identity_values_reverse_lookup():
    """_update_selected should accept identity values and reverse-lookup row numbers for CDS."""
    print()
    print("Test 4: _update_selected accepts identity values → reverse lookup to row numbers")
    print("=" * 70)

    from holoviews.plotting.bokeh.plot import BokehPlot
    from bokeh.models import ColumnDataSource

    df = pd.DataFrame(
        {"x": [1, 2, 3, 4, 5], "y": [10, 20, 30, 40, 50]},
        index=pd.Index(["p", "q", "r", "s", "t"], name="uid"),
    )

    hv_ids = list(df.index.values)
    cds = ColumnDataSource(
        data={"x": df["x"].tolist(), "y": df["y"].tolist(), "_hv_id": hv_ids}
    )
    print(f"CDS columns: {list(cds.data.keys())}")
    print(f"CDS _hv_id values: {list(cds.data['_hv_id'])}")
    print()

    class FakePlot:
        selected = None
        callbacks = []
        _hv_selected_ids = []
        def param_warning(self, msg):
            pass

    # Test 1: pass in identity values → should reverse lookup row numbers
    plot = FakePlot()
    plot.selected = ["p", "r", "t"]
    print(f"Case 1: plot.selected = identity values {plot.selected}")
    BokehPlot._update_selected(plot, cds)
    print(f"  → CDS selected.indices: {cds.selected.indices}")
    print(f"  → plot._hv_selected_ids: {plot._hv_selected_ids}")
    assert cds.selected.indices == [0, 2, 4], f"Expected [0, 2, 4], got {cds.selected.indices}"
    assert plot._hv_selected_ids == ["p", "r", "t"], (
        f"Internal _hv_selected_ids should be identity values ['p','r','t'], got {plot._hv_selected_ids}"
    )

    # Test 2: pass in row numbers → should keep row numbers, also extract identity values
    cds.selected.indices = []
    plot2 = FakePlot()
    plot2.selected = [1, 3]
    print(f"Case 2: plot.selected = row numbers {plot2.selected}")
    BokehPlot._update_selected(plot2, cds)
    print(f"  → CDS selected.indices: {cds.selected.indices}")
    print(f"  → plot._hv_selected_ids: {plot2._hv_selected_ids}")
    assert cds.selected.indices == [1, 3], f"Expected [1, 3], got {cds.selected.indices}"
    assert plot2._hv_selected_ids == ["q", "s"], (
        f"Internal _hv_selected_ids should be ['q','s'], got {plot2._hv_selected_ids}"
    )

    print()
    print("PASS: _update_selected correctly handles both row numbers and identity values")


def test_end_to_end_cds_has_hv_id_and_streams_get_row_numbers():
    """End-to-end: rendered CDS has _hv_id, but Selection1D streams receive row numbers."""
    print()
    print("Test 5: End-to-end → CDS has _hv_id, streams get row numbers")
    print("=" * 70)

    df = pd.DataFrame(
        {"category": ["A", "B", "A", "B", "A", "B"], "value": [10, 20, 30, 40, 50, 60]},
        index=pd.Index([101, 102, 103, 104, 105, 106], name="row_id"),
    )

    points = hv.Points(df, kdims=["value", "value"], vdims=["category"]).opts(
        tools=["box_select", "tap"]
    )
    table = hv.Table(df, kdims=["category"], vdims=["value"])

    ls = link_selections.instance()
    layout = ls(points + table)

    from bokeh.models import ColumnDataSource
    plot = hv.render(layout)
    sources = [m for m in plot.select({"type": ColumnDataSource}) if "_hv_id" in m.data]

    print(f"Found {len(sources)} CDS(s) with _hv_id column")
    for i, s in enumerate(sources):
        print(f"  CDS {i}: _hv_id = {list(s.data['_hv_id'])}")

    assert len(sources) >= 2, "At least 2 CDSs (points + table) should have _hv_id"

    # Verify the identity values in CDS match DataFrame index
    for s in sources:
        assert list(s.data["_hv_id"]) == [101, 102, 103, 104, 105, 106], (
            f"CDS _hv_id should match DataFrame index [101..106], got {list(s.data['_hv_id'])}"
        )

    print()
    print("PASS: Rendered CDS contains correct _hv_id identity values")


if __name__ == "__main__":
    test_row_numbers_preserved_in_selection1d_stream()
    test_selection_expr_built_from_row_numbers_maps_by_identity()
    test_index_cols_priority_over_dataframe_index()
    test_update_selected_with_identity_values_reverse_lookup()
    test_end_to_end_cds_has_hv_id_and_streams_get_row_numbers()
    print()
    print("=" * 70)
    print("ALL TESTS PASSED!")
    print("=" * 70)
