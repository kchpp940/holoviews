from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import pytest

from holoviews.core.util.capabilities import (
    CapabilityDiagnostic,
    CapabilityType,
    get_backend_capability,
    get_datashader_capability,
)
from holoviews.core.util.dependencies import _is_installed


def optional_dependencies(*names: str):
    if not all(map(_is_installed, names)):
        return None
    try:
        return importlib.import_module(names[0])
    except Exception:
        return None


def _skip_reason_from_diag(diag: CapabilityDiagnostic) -> str:
    if diag.available:
        return ""
    return diag.format_skip_reason()


if TYPE_CHECKING:
    import cftime
    import dask
    import dask.array as da
    import dask.dataframe as dd
    import datashader as ds
    import duckdb
    import ibis
    import IPython
    import matplotlib as mpl
    import networkx as nx
    import notebook
    import pandas as pd
    import plotly
    import polars as pl
    import pyarrow as pa
    import scipy
    import shapely
    import spatialpandas as spd
    import tsdownsample
    import xarray as xr
    import xyzservices
else:
    cftime = optional_dependencies("cftime")
    dask = optional_dependencies("dask")
    da = optional_dependencies("dask.array")
    dd = optional_dependencies("dask.dataframe", "pyarrow")
    ds = optional_dependencies("datashader")
    duckdb = optional_dependencies("duckdb")
    ibis = optional_dependencies("ibis")
    IPython = optional_dependencies("IPython")
    mpl = optional_dependencies("matplotlib")
    nx = optional_dependencies("networkx")
    notebook = optional_dependencies("notebook")
    pd = optional_dependencies("pandas")
    plotly = optional_dependencies("plotly")
    pl = optional_dependencies("polars")
    pa = optional_dependencies("pyarrow")
    scipy = optional_dependencies("scipy")
    shapely = optional_dependencies("shapely")
    spd = optional_dependencies("spatialpandas")
    tsdownsample = optional_dependencies("tsdownsample")
    xr = optional_dependencies("xarray")
    xyzservices = optional_dependencies("xyzservices")


_skip = lambda module, name: pytest.mark.skipif(module is None, reason=f"{name} is not installed")
cftime_skip = _skip(cftime, "cftime")
dask_skip = _skip(dask, "dask")
da_skip = _skip(da, "dask.array")
dd_skip = _skip(dd, "dask.dataframe")
duckdb_skip = _skip(duckdb, "duckdb")
ibis_skip = _skip(ibis, "ibis")
ipython_skip = _skip(IPython, "IPython")
nx_skip = _skip(nx, "networkx")
notebook_skip = _skip(notebook, "notebook")
pd_skip = _skip(pd, "pandas")
pl_skip = _skip(pl, "polars")
pa_skip = _skip(pa, "pyarrow")
scipy_skip = _skip(scipy, "scipy")
shapely_skip = _skip(shapely, "shapely")
spd_skip = _skip(spd, "spatialpandas")
tsdownsample_skip = _skip(tsdownsample, "tsdownsample")
xr_skip = _skip(xr, "xarray")
xyzservices_skip = _skip(xyzservices, "xyzservices")


def _backend_skip(backend: str) -> pytest.mark:
    diag = get_backend_capability(backend)
    if diag.available:
        return pytest.mark.skipif(False, reason="")
    reason = _skip_reason_from_diag(diag)
    return pytest.mark.skipif(True, reason=reason)


bokeh_skip = _backend_skip("bokeh")
mpl_skip = _backend_skip("matplotlib")
plotly_skip = _backend_skip("plotly")

_ds_diag = get_datashader_capability()
if _ds_diag.available:
    ds_skip = pytest.mark.skipif(False, reason="")
else:
    ds_skip = pytest.mark.skipif(True, reason=_skip_reason_from_diag(_ds_diag))


if spd:
    import multiprocessing.resource_tracker  # noqa: F401
