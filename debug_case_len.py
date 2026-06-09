import warnings
warnings.filterwarnings("ignore")
import pandas as pd

cases = [
    ("Default RangeIndex", pd.DataFrame({"x": [1, 2, 3], "y": [10, 20, 30]})),
    ("Unnamed Int64Index", pd.DataFrame({"x": [1,2,3], "y": [10,20,30]}, index=pd.Index([10, 20, 30]))),
    ("Named RangeIndex non-default", pd.DataFrame({"x": [1,2,3], "y": [10,20,30]}, index=pd.RangeIndex(100, 103, name="rid"))),
    ("Filtered view", pd.DataFrame({"x": list(range(10)), "y": list(range(10))}, index=pd.RangeIndex(100, 110)).iloc[3:7]),
    ("Unnamed string Index", pd.DataFrame({"x": [1,2,3], "y": [10,20,30]}, index=pd.Index(["a", "b", "c"]))),
    ("Unnamed MultiIndex", pd.DataFrame({"x": [1,2,3], "y": [10,20,30]}, index=pd.MultiIndex.from_tuples([("a",1),("b",2),("c",3)]))),
    ("Default RangeIndex + kdims", pd.DataFrame({"cat": ["A","B","A"], "val": [10,20,30]}), ["cat"], ["val"]),
]

for i, case in enumerate(cases):
    print(f"Case {i}: len={len(case)}, type[0]={type(case[0]).__name__}")
    if len(case) == 4:
        name, df, kdims, vdims = case
        print(f"  -> matched len==4: name={name}, kdims={kdims}, vdims={vdims}")
    elif len(case) == 3:
        print(f"  -> len==3")
    elif len(case) == 2:
        name, df = case
        print(f"  -> matched len==2: name={name}")
    else:
        print(f"  -> else, len={len(case)}")
