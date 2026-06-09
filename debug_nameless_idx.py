import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np

# Unnamed non-default index
df = pd.DataFrame({"x": [1, 2, 3]}, index=pd.Index([10, 20, 30]))
print("df.index.names:", df.index.names)
print("list(df.index.names):", list(df.index.names))
print("None in df.index.names:", None in df.index.names)
print("None in df.columns:", None in df.columns)

# Test get_level_values(None)
try:
    vals = df.index.get_level_values(None)
    print("get_level_values(None):", list(vals))
except Exception as e:
    print("get_level_values(None) ERROR:", e)

# Test get_level_values(0)
try:
    vals = df.index.get_level_values(0)
    print("get_level_values(0):", list(vals))
except Exception as e:
    print("get_level_values(0) ERROR:", e)

# MultiIndex unnamed
df2 = pd.DataFrame({"x": [1, 2, 3]}, index=pd.MultiIndex.from_tuples([("a", 1), ("b", 2), ("c", 3)]))
print()
print("MultiIndex names:", df2.index.names)
print("list(df2.index.names):", list(df2.index.names))
