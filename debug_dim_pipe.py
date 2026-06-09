import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
import holoviews as hv
from holoviews.util.transform import dim

df = pd.DataFrame({'x': [1, 2, 3, 4], 'y': [10, 20, 30, 40]}, index=pd.Index(['a', 'b', 'c', 'd'], name='idx'))
table = hv.Table(df)

sel_ids = ['a', 'c']
def mask_by_index(df_or_data):
    print(f"  mask_by_index called with type: {type(df_or_data)}")
    if isinstance(df_or_data, pd.DataFrame):
        print(f"    DataFrame index: {df_or_data.index.tolist()}")
        result = df_or_data.index.get_level_values('idx').isin(sel_ids)
        print(f"    isin result type: {type(result)}")
        return np.asarray(result)
    else:
        print(f"    Not a DataFrame, data: {df_or_data}")
        return np.array([False] * len(df_or_data))

print('=== Testing dim.pipe(mask_by_index, "*") ===')
try:
    expr = dim.pipe(mask_by_index, '*')
    print('expr:', expr)
    mask = expr.apply(table.dataset, expanded=True, flat=True)
    print('mask:', mask)
except Exception as e:
    import traceback
    print('ERROR:')
    traceback.print_exc()
