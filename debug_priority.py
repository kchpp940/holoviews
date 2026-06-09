import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
import holoviews as hv

df = pd.DataFrame(
    {"user_id": [101, 102, 103, 101, 102, 103], "session": [1, 1, 1, 2, 2, 2], "score": [85, 90, 78, 92, 88, 81]},
    index=pd.Index([1000, 1001, 1002, 1003, 1004, 1005], name="df_row_id"),
)

table = hv.Table(df, kdims=["user_id", "session"], vdims=["score"])
print(f"table dimensions: {[d.name for d in table.dimensions()]}")
print(f"table.kdims: {[d.name for d in table.kdims]}")

print()
cols = ["user_id", "session"]
print(f"cols = {cols}")
for c in cols:
    dim = table.get_dimension(c)
    print(f"  dim('{c}'): {dim}")
    if dim is not None:
        vals = table.dimension_values(c, expanded=False)
        print(f"    values: {list(vals)}")

print()
vals = [table.dimension_values(c, expanded=False) for c in cols]
print(f"vals list: {[list(v) for v in vals]}")
zipped = list(zip(*vals))
print(f"zipped: {zipped}")

print()
print("_get_identity_values explicit:")
result = table._get_identity_values(index_cols=cols)
print(f"  result: {result}")
print(f"  len: {len(result)}")
