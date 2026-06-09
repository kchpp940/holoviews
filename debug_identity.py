import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import holoviews as hv

df = pd.DataFrame({'x': [1, 2, 3, 4], 'y': [10, 20, 30, 40]}, index=pd.Index(['a', 'b', 'c', 'd'], name='idx'))
table = hv.Table(df)
print('table.data type:', type(table.data))
print('table.data.index.names:', table.data.index.names)
identity_cols = table._get_identity_columns()
print('identity_cols:', identity_cols)
print('all in dims?:', all(table.get_dimension(c) is not None for c in identity_cols))
for c in identity_cols:
    print(f'  dim {c}:', table.get_dimension(c))
print('idx in data.index.names:', 'idx' in table.data.index.names)
print('idx in data.columns:', 'idx' in table.data.columns)
print('table.dataset type:', type(table.dataset))
print('table.dataset.data type:', type(table.dataset.data))

print()
print('=== Now calling _get_index_selection ===')
expr, a, b = table._get_index_selection(['a', 'c'], index_cols=None)
print('expr:', expr)
print()
print('=== Testing apply on table.dataset ===')
try:
    mask = expr.apply(table.dataset, expanded=True, flat=True)
    print('mask:', mask)
except Exception as e:
    print('ERROR:', type(e).__name__, e)

print()
print('=== Testing apply on table (element itself) ===')
try:
    mask = expr.apply(table, expanded=True, flat=True)
    print('mask:', mask)
except Exception as e:
    print('ERROR:', type(e).__name__, e)
