import warnings
warnings.filterwarnings("ignore")
import holoviews.element.selection as s
import holoviews.plotting.bokeh.plot as p
import holoviews as hv
import pandas as pd
import numpy as np

hv.extension("bokeh")

print("Shared helpers exported:")
print("  _is_default_dataframe_index:", hasattr(s, "_is_default_dataframe_index"))
print("  get_identity_columns:", hasattr(s, "get_identity_columns"))
print("  get_identity_values:", hasattr(s, "get_identity_values"))

print()
print("BokehPlot uses shared helper:", "get_identity_values" in p.BokehPlot._get_identity_values.__code__.co_names)

df = pd.DataFrame({"x": [1,2,3], "y": [10,20,30]}, index=pd.RangeIndex(100, 103))
t = hv.Table(df, kdims=["x"], vdims=["y"])
kdim_names = [d.name for d in t.kdims]
all_dim_names = [d.name for d in t.dimensions()]

print()
print("identity_cols:", s.get_identity_columns(t, None, kdim_names, all_dim_names))
print("identity_values:", s.get_identity_values(t))

expr, _, _ = t._get_index_selection([0, 2], None)
print()
print("selection expr:", expr)
mask = expr.apply(t.dataset, expanded=True, flat=True)
print("selected:", list(np.where(mask)[0]))
print()
print("All OK")
