import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
import holoviews as hv

hv.extension("bokeh")

cases = []

# Case 1: Default RangeIndex (should fall back to kdims or range)
cases.append(("Default RangeIndex", pd.DataFrame({"x": [1, 2, 3], "y": [10, 20, 30]})))

# Case 2: Unnamed non-default integer index
cases.append(("Unnamed Int64Index([10,20,30])", pd.DataFrame({"x": [1,2,3], "y": [10,20,30]}, index=pd.Index([10, 20, 30]))))

# Case 3: Named RangeIndex starting from 100
cases.append(("Named RangeIndex(100,103)", pd.DataFrame({"x": [1,2,3], "y": [10,20,30]}, index=pd.RangeIndex(100, 103, name="rid"))))

# Case 4: Filtered view (original non-default index preserved)
df_full = pd.DataFrame({"x": list(range(10)), "y": list(range(10))}, index=pd.RangeIndex(100, 110))
cases.append(("Filtered view (iloc[3:7])", df_full.iloc[3:7]))

# Case 5: Unnamed string Index
cases.append(("Unnamed string Index(['a','b','c'])", pd.DataFrame({"x": [1,2,3], "y": [10,20,30]}, index=pd.Index(["a", "b", "c"]))))

# Case 6: Unnamed MultiIndex
cases.append(("Unnamed MultiIndex", pd.DataFrame({"x": [1,2,3], "y": [10,20,30]}, index=pd.MultiIndex.from_tuples([("a",1),("b",2),("c",3)]))))

# Case 7: Default RangeIndex but kdims given
df7 = pd.DataFrame({"cat": ["A","B","A"], "val": [10,20,30]})
cases.append(("Default RangeIndex with kdims", df7))

for name, df in cases:
    print(f"=== {name} ===")
    print(f"  index: {df.index}")
    print(f"  index.names: {df.index.names}")
    try:
        if name.endswith("kdims"):
            t = hv.Table(df, kdims=["cat"], vdims=["val"])
        else:
            t = hv.Table(df, kdims=["x"], vdims=["y"])
        cols = t._get_identity_columns()
        vals = t._get_identity_values()
        print(f"  identity columns: {cols}")
        print(f"  identity values:  {vals}")

        # Test selection expression
        expr, _, _ = t._get_index_selection([0, len(t)-1], index_cols=None)
        if expr is not None:
            mask = expr.apply(t.dataset, expanded=True, flat=True)
            sel = list(np.where(mask)[0])
            print(f"  select first+last row: {sel}")
        print("  OK")
    except Exception as e:
        import traceback
        print(f"  ERROR: {e}")
        traceback.print_exc()
    print()
