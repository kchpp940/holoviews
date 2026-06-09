"""Cross-element selection with non-default index and duplicate kdims."""
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
import holoviews as hv
from holoviews.selection import link_selections

hv.extension("bokeh")

print("=== Scenario 1: Filtered view with preserved non-default index ===")
df_full = pd.DataFrame(
    {"x": list(range(10)), "y": list(range(10))},
    index=pd.RangeIndex(100, 110),  # unnamed, non-default RangeIndex
)
df_subset = df_full.iloc[::2].copy()  # rows 100, 102, 104, 106, 108

print(f"Full index:   {list(df_full.index)}")
print(f"Subset index: {list(df_subset.index)}")
print()

t_full = hv.Table(df_full, kdims=["x"], vdims=["y"])
t_sub = hv.Table(df_subset, kdims=["x"], vdims=["y"])

print(f"Full table identity columns: {t_full._get_identity_columns()}")
print(f"Full table identity values:  {t_full._get_identity_values()}")
print(f"Subset identity columns:     {t_sub._get_identity_columns()}")
print(f"Subset identity values:      {t_sub._get_identity_values()}")
print()

# Select rows 0 and 3 in the FULL table (index values 100 and 103)
row_nums_full = [0, 3]
expected_ids = {df_full.index[i] for i in row_nums_full}
print(f"Selected rows on FULL table: {row_nums_full} → index values {expected_ids}")

expr, _, _ = t_full._get_index_selection(row_nums_full, index_cols=None)
mask_full = expr.apply(t_full.dataset, expanded=True, flat=True)
mask_sub = expr.apply(t_sub.dataset, expanded=True, flat=True)
sel_full = list(np.where(mask_full)[0])
sel_sub = list(np.where(mask_sub)[0])

full_ids = {df_full.index[i] for i in sel_full}
sub_ids = {df_subset.index[i] for i in sel_sub}
print(f"  → FULL selected: rows {sel_full}, index vals {full_ids}")
print(f"  → SUBSET selected: rows {sel_sub}, index vals {sub_ids}")

assert full_ids == expected_ids, f"Full ids {full_ids} != expected {expected_ids}"
assert sub_ids.issubset(expected_ids), f"Sub ids {sub_ids} not subset of {expected_ids}"
# Only 100 is in the subset (103 is not, since subset takes every 2nd: 100,102,104,106,108)
assert sub_ids == {100}, f"Expected subset to match only 100, got {sub_ids}"
print("PASS\n")


print("=== Scenario 2: Duplicate kdims but non-default DataFrame index ===")
df_dup = pd.DataFrame(
    {"category": ["A", "A", "B", "B", "A"], "value": [10, 20, 30, 40, 50]},
    index=pd.Index([9001, 9002, 9003, 9004, 9005]),  # unnamed, unique
)
print(df_dup)
print()

t = hv.Table(df_dup, kdims=["category"], vdims=["value"])
print(f"kdims (category) values: {t.dimension_values('category', expanded=True).tolist()}")
print(f"identity columns: {t._get_identity_columns()}")
print(f"identity values:  {t._get_identity_values()}")
print()

# Select rows 0 and 4 (both have category='A', but different index values)
row_nums = [0, 4]
expected_ids = {df_dup.index[i] for i in row_nums}
print(f"Selected rows {row_nums} → index values {expected_ids}")
print(f"  Both rows have category='A' — if identity used kdims, would select ALL 'A' rows")

expr, _, _ = t._get_index_selection(row_nums, index_cols=None)
mask = expr.apply(t.dataset, expanded=True, flat=True)
sel = list(np.where(mask)[0])
got_ids = {df_dup.index[i] for i in sel}
print(f"  → Actually selected rows: {sel}, index vals: {got_ids}")

assert got_ids == expected_ids, (
    f"Got {got_ids}, expected {expected_ids}. "
    f"Should NOT select row 1 (index 9002, also category='A')"
)
assert sel == [0, 4], f"Expected [0,4], got {sel}"
print("PASS: Only the two specifically selected rows are matched, not all rows with duplicate category\n")


print("=== Scenario 3: End-to-end Bokeh render — CDS _hv_id values ===")
df_plot = pd.DataFrame(
    {"cat": ["X", "Y", "X", "Y"], "val": [1, 2, 3, 4]},
    index=pd.RangeIndex(50, 54),
)
points = hv.Points(df_plot, kdims=["val", "val"], vdims=["cat"]).opts(tools=["tap"])
table = hv.Table(df_plot, kdims=["cat"], vdims=["val"])
ls = link_selections.instance()
layout = ls(points + table)

from bokeh.models import ColumnDataSource
plot = hv.render(layout)
sources = [m for m in plot.select({"type": ColumnDataSource}) if "_hv_id" in m.data]
print(f"CDS sources with _hv_id: {len(sources)}")
for i, s in enumerate(sources):
    ids = list(s.data["_hv_id"])
    print(f"  CDS {i} _hv_id = {ids}")
    assert ids == [50, 51, 52, 53], f"Expected [50,51,52,53], got {ids}"
print("PASS: CDS _hv_id contains correct non-default index values\n")

print("=== ALL SCENARIOS PASSED ===")
