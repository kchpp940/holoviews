"""End-to-end test for Bokeh linked selections with identity columns."""
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import holoviews as hv
from holoviews.selection import link_selections

hv.extension("bokeh")

def test_end_to_end_link_selections_duplicate_categories():
    """End-to-end test: duplicate category values with DataFrame unique index."""
    print("End-to-end test: duplicate categories + unique DataFrame index")
    print("=" * 70)

    np.random.seed(42)
    n = 20
    df = pd.DataFrame({
        'category': ['A', 'B'] * 10,
        'value': np.random.randn(n),
        'group': ['X', 'X', 'Y', 'Y'] * 5,
    }, index=pd.RangeIndex(100, 100 + n, name='row_id'))

    print(f"DataFrame shape: {df.shape}")
    print(f"DataFrame index: {df.index.tolist()[:5]}...")
    print(f"category unique: {df['category'].unique()}")
    print(f"group unique: {df['group'].unique()}")
    print(f"category+group combos: {df[['category', 'group']].drop_duplicates().shape[0]} unique out of {len(df)}")
    print()

    points = hv.Points(df, kdims=['value', 'value'], vdims=['category', 'group']).opts(tools=['box_select', 'tap'])
    table = hv.Table(df, kdims=['category', 'group'], vdims=['value'])

    ls = link_selections.instance()
    layout = ls(points + table)

    print("Created link_selections layout")

    plot = hv.render(layout)
    print(f"Rendered plot type: {type(plot)}")
    print()

    from bokeh.models import ColumnDataSource
    sources = [m for m in plot.select({'type': ColumnDataSource})]
    print(f"Found {len(sources)} ColumnDataSource(s)")
    for i, s in enumerate(sources):
        print(f"  CDS {i}: columns = {list(s.data.keys())}")
        if '_hv_id' in s.data:
            print(f"    _hv_id values (first 5): {list(s.data['_hv_id'])[:5]}")
    print()

    assert any('_hv_id' in s.data for s in sources), "At least one CDS should have _hv_id column"

    sel_expr = ls.selection_expr
    print(f"Initial selection_expr: {sel_expr}")

    from holoviews.streams import Selection1D
    sel_stream = Selection1D(source=points, index=[100, 101, 105])
    print(f"Simulated Selection1D with index=[100, 101, 105] (DataFrame index values)")

    expr, _, _ = points._get_index_selection([100, 101, 105], index_cols=None)
    print(f"Generated selection expression: {expr}")

    mask_points = expr.apply(points.dataset, expanded=True, flat=True)
    mask_table = expr.apply(table.dataset, expanded=True, flat=True)

    selected_rows_points = list(np.where(mask_points)[0])
    selected_rows_table = list(np.where(mask_table)[0])

    print(f"Selected rows in Points: {selected_rows_points}")
    print(f"Selected rows in Table:  {selected_rows_table}")

    expected = [0, 1, 5]
    assert selected_rows_points == expected, f"Points expected {expected}, got {selected_rows_points}"
    assert selected_rows_table == expected, f"Table expected {expected}, got {selected_rows_table}"
    print()
    print("PASS: Both Points and Table select the same rows by DataFrame index identity")

def test_end_to_end_filtered_view():
    """End-to-end test: filtered DataFrame view with original index preserved."""
    print()
    print("End-to-end test: filtered view preserves original index identity")
    print("=" * 70)

    df_full = pd.DataFrame({
        'x': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        'y': [10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
    }, index=pd.Index(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j'], name='uid'))

    df_filtered = df_full[df_full['x'] > 5].copy()
    print(f"Full DataFrame: {len(df_full)} rows, index={df_full.index.tolist()}")
    print(f"Filtered DataFrame: {len(df_filtered)} rows, index={df_filtered.index.tolist()}")
    print()

    table_full = hv.Table(df_full)
    table_filtered = hv.Table(df_filtered)

    expr, _, _ = table_full._get_index_selection(['f', 'h', 'j'], index_cols=None)

    mask_full = expr.apply(table_full.dataset, expanded=True, flat=True)
    mask_filtered = expr.apply(table_filtered.dataset, expanded=True, flat=True)

    sel_full = list(np.where(mask_full)[0])
    sel_filtered = list(np.where(mask_filtered)[0])

    print(f"Selection on full table: rows {sel_full}")
    print(f"Selection on filtered table: rows {sel_filtered}")
    print(f"  Full table identities: {[df_full.index[i] for i in sel_full]}")
    print(f"  Filtered table identities: {[df_filtered.index[i] for i in sel_filtered]}")

    assert sel_full == [5, 7, 9], f"Full table expected [5, 7, 9], got {sel_full}"
    assert sel_filtered == [0, 2, 4], f"Filtered table expected [0, 2, 4], got {sel_filtered}"

    full_ids = set(df_full.index[i] for i in sel_full)
    filtered_ids = set(df_filtered.index[i] for i in sel_filtered)
    assert full_ids == filtered_ids == {'f', 'h', 'j'}, f"Identity mismatch: {full_ids} vs {filtered_ids}"
    print()
    print("PASS: Selection by identity correctly maps across differently-sized datasets")

def test_end_to_end_explicit_index_cols():
    """End-to-end test: explicit index_cols parameter."""
    print()
    print("End-to-end test: explicit index_cols")
    print("=" * 70)

    df = pd.DataFrame({
        'user_id': [101, 102, 103, 101, 102, 103],
        'session': [1, 1, 1, 2, 2, 2],
        'score': [85, 90, 78, 92, 88, 81],
    })

    print(f"DataFrame:\n{df}")
    print()
    print(f"user_id is not unique: {df['user_id'].duplicated().any()}")
    print(f"user_id+session unique: {not df[['user_id', 'session']].duplicated().any()}")
    print()

    table = hv.Table(df, kdims=['user_id', 'session'], vdims=['score'])

    expr1, _, _ = table._get_index_selection([101], index_cols=['user_id'])
    mask1 = expr1.apply(table.dataset, expanded=True, flat=True)
    sel1 = list(np.where(mask1)[0])
    print(f"Selecting user_id=101: rows {sel1} (should be [0, 3])")
    assert sel1 == [0, 3], f"Expected [0, 3], got {sel1}"

    expr2, _, _ = table._get_index_selection([(101, 1), (103, 2)], index_cols=['user_id', 'session'])
    mask2 = expr2.apply(table.dataset, expanded=True, flat=True)
    sel2 = list(np.where(mask2)[0])
    print(f"Selecting (101,1)+(103,2): rows {sel2} (should be [0, 5])")
    assert sel2 == [0, 5], f"Expected [0, 5], got {sel2}"

    print()
    print("PASS: Explicit index_cols correctly identify unique rows")


if __name__ == "__main__":
    test_end_to_end_link_selections_duplicate_categories()
    test_end_to_end_filtered_view()
    test_end_to_end_explicit_index_cols()
    print()
    print("=" * 70)
    print("ALL END-TO-END TESTS PASSED!")
    print("=" * 70)
