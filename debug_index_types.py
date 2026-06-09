import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np

# Case 1: Default RangeIndex
df1 = pd.DataFrame({"x": [1, 2, 3]})
print("Case 1 - Default RangeIndex:")
print(f"  index: {df1.index}")
print(f"  type: {type(df1.index)}")
print(f"  names: {df1.index.names}")
print(f"  isinstance RangeIndex: {isinstance(df1.index, pd.RangeIndex)}")
print(f"  start={df1.index.start}, stop={df1.index.stop}, step={df1.index.step}")
print(f"  equals range(n): {list(df1.index) == list(range(len(df1)))}")
print()

# Case 2: Named RangeIndex starting from 100
df2 = pd.DataFrame({"x": [1, 2, 3]}, index=pd.RangeIndex(100, 103, name="rid"))
print("Case 2 - Named RangeIndex(100,103):")
print(f"  index: {df2.index}")
print(f"  type: {type(df2.index)}")
print(f"  names: {df2.index.names}")
print(f"  isinstance RangeIndex: {isinstance(df2.index, pd.RangeIndex)}")
print(f"  start={df2.index.start}, stop={df2.index.stop}, step={df2.index.step}")
print(f"  equals range(n): {list(df2.index) == list(range(len(df2)))}")
print()

# Case 3: Unnamed Int64Index (non-default)
df3 = pd.DataFrame({"x": [1, 2, 3]}, index=pd.Index([10, 20, 30]))
print("Case 3 - Unnamed Int64Index([10,20,30]):")
print(f"  index: {df3.index}")
print(f"  type: {type(df3.index)}")
print(f"  names: {df3.index.names}")
print(f"  isinstance RangeIndex: {isinstance(df3.index, pd.RangeIndex)}")
print(f"  equals range(n): {list(df3.index) == list(range(len(df3)))}")
print()

# Case 4: Filtered view (original index preserved)
df_full = pd.DataFrame({"x": list(range(10))}, index=pd.RangeIndex(100, 110))
df4 = df_full.iloc[3:7]
print("Case 4 - Filtered view from RangeIndex(100,110), iloc[3:7]:")
print(f"  index: {df4.index}")
print(f"  type: {type(df4.index)}")
print(f"  names: {df4.index.names}")
print(f"  isinstance RangeIndex: {isinstance(df4.index, pd.RangeIndex)}")
print(f"  equals range(n): {list(df4.index) == list(range(len(df4)))}")
print()

# Case 5: String index, unnamed
df5 = pd.DataFrame({"x": [1, 2, 3]}, index=pd.Index(["a", "b", "c"]))
print("Case 5 - Unnamed string Index(['a','b','c']):")
print(f"  index: {df5.index}")
print(f"  type: {type(df5.index)}")
print(f"  names: {df5.index.names}")
print(f"  isinstance RangeIndex: {isinstance(df5.index, pd.RangeIndex)}")
print(f"  equals range(n): {list(df5.index) == list(range(len(df5)))}")
print()

def is_default_range_index(idx, n):
    """Check if idx is the default RangeIndex(0, n, 1) or equivalent."""
    if isinstance(idx, pd.RangeIndex):
        return idx.start == 0 and idx.step == 1 and idx.stop == n
    # Also check if it's a plain integer index matching range(n)
    try:
        return list(idx) == list(range(n))
    except Exception:
        return False

print("Testing is_default_range_index:")
for i, df in enumerate([df1, df2, df3, df4, df5], 1):
    print(f"  Case {i}: {is_default_range_index(df.index, len(df))}")
