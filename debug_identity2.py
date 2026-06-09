import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import holoviews as hv

df = pd.DataFrame({'x': [1, 2, 3, 4], 'y': [10, 20, 30, 40]}, index=pd.Index(['a', 'b', 'c', 'd'], name='idx'))
table = hv.Table(df)

identity_cols = table._get_identity_columns()
print('identity_cols:', identity_cols)
print('isinstance(table.data, pd.DataFrame):', isinstance(table.data, pd.DataFrame))

try:
    for c in identity_cols:
        print(f"  c '{c}' in data.index.names: {c in table.data.index.names}")
        print(f"  c '{c}' in data.columns: {c in table.data.columns}")
    check = all(
        c in table.data.index.names and c not in table.data.columns
        for c in identity_cols
    )
    print('all condition result:', check)
except Exception as e:
    print('all condition ERROR:', e)

# Now let's trace into _get_index_selection
sel_ids = ['a', 'c']
try:
    def _make_mask(ds, id_cols=identity_cols, ids=sel_ids):
        df = ds.data
        if len(id_cols) == 1:
            return df.index.get_level_values(id_cols[0]).isin(ids).values
        else:
            idx_tuples = list(df.index.to_flat_index())
            return np.array([t in ids for t in idx_tuples])

    from holoviews.util.transform import dim
    expr = dim(_make_mask, object=True)
    print('custom mask dim:', expr)
    mask = expr.apply(table.dataset, expanded=True, flat=True)
    print('mask result:', mask)
except Exception as e:
    import traceback
    print('ERROR in custom mask:')
    traceback.print_exc()
