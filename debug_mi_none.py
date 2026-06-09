import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np

df_mi = pd.DataFrame(
    {"x": [1, 2, 3]},
    index=pd.MultiIndex.from_tuples([("a", 1), ("b", 2), ("c", 3)]),
)
print("MultiIndex names:", df_mi.index.names)

try:
    vals = df_mi.index.get_level_values(None)
    print("get_level_values(None):", list(vals))
except Exception as e:
    print("get_level_values(None) ERROR:", e)

try:
    vals = df_mi.index.to_flat_index()
    print("to_flat_index():", list(vals))
except Exception as e:
    print("to_flat_index() ERROR:", e)
