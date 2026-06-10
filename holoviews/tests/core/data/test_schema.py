from __future__ import annotations

import datetime

import numpy as np
import pytest

import holoviews as hv


_SCHEMA_FIELDS = frozenset(
    {"name", "dtype", "is_categorical", "is_datetime", "is_nullable", "range", "unique_count", "missing_count"}
)


def _assert_schema_fields(schema_entry):
    missing = _SCHEMA_FIELDS - set(schema_entry)
    assert not missing, f"Schema entry missing fields: {missing}"


class TestDatasetSchemaDictionary:
    def setup_method(self):
        self.restore_datatype = hv.Dataset.datatype
        hv.Dataset.datatype = ["dictionary"]

    def teardown_method(self):
        hv.Dataset.datatype = self.restore_datatype

    def test_schema_basic_structure(self):
        ds = hv.Dataset({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}, kdims=["x"], vdims=["y"])
        schema = ds.schema()
        assert "kdims" in schema
        assert "vdims" in schema
        assert len(schema["kdims"]) == 1
        assert len(schema["vdims"]) == 1

    def test_schema_kdim_fields(self):
        ds = hv.Dataset({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        _assert_schema_fields(kdim_schema)
        assert kdim_schema["name"] == "x"
        assert "int" in kdim_schema["dtype"]
        assert kdim_schema["is_categorical"] == False
        assert kdim_schema["is_datetime"] == False
        assert kdim_schema["unique_count"] == 3
        assert kdim_schema["missing_count"] == 0

    def test_schema_vdim_fields(self):
        ds = hv.Dataset({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}, kdims=["x"], vdims=["y"])
        vdim_schema = ds.schema()["vdims"][0]
        _assert_schema_fields(vdim_schema)
        assert vdim_schema["name"] == "y"
        assert "float" in vdim_schema["dtype"]
        assert vdim_schema["is_categorical"] == False
        assert vdim_schema["is_datetime"] == False
        assert vdim_schema["is_nullable"] == True
        assert vdim_schema["range"] == (4.0, 6.0)
        assert vdim_schema["unique_count"] == 3
        assert vdim_schema["missing_count"] == 0

    def test_schema_missing_values_float(self):
        ds = hv.Dataset(
            {"x": [1, 2, 3], "y": [4.0, float("nan"), 6.0]}, kdims=["x"], vdims=["y"]
        )
        vdim_schema = ds.schema()["vdims"][0]
        assert vdim_schema["missing_count"] == 1

    def test_schema_range(self):
        ds = hv.Dataset({"x": [10, 20, 30], "y": [1.0, 2.0, 3.0]}, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["range"] == (10, 30)

    def test_schema_unique_count(self):
        ds = hv.Dataset({"x": [1, 1, 2, 3], "y": [4.0, 5.0, 6.0, 7.0]}, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["unique_count"] == 3

    def test_schema_categorical(self):
        ds = hv.Dataset(
            {"cat": ["a", "b", "c"], "val": [1, 2, 3]}, kdims=["cat"], vdims=["val"]
        )
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["is_categorical"] == True
        assert kdim_schema["is_datetime"] == False

    def test_schema_datetime(self):
        dates = np.array(["2023-01-01", "2023-01-02", "2023-01-03"], dtype="datetime64[ns]")
        ds = hv.Dataset({"t": dates, "val": [1, 2, 3]}, kdims=["t"], vdims=["val"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["is_datetime"] == True
        assert kdim_schema["is_categorical"] == False

    def test_schema_nullable_float(self):
        ds = hv.Dataset({"x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0]}, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["is_nullable"] == True

    def test_schema_non_nullable_int(self):
        ds = hv.Dataset({"x": [1, 2, 3], "y": [4, 5, 6]}, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["is_nullable"] == False

    def test_schema_multiple_vdims(self):
        ds = hv.Dataset(
            {"x": [1, 2, 3], "y1": [4.0, 5.0, 6.0], "y2": [7.0, 8.0, 9.0]},
            kdims=["x"],
            vdims=["y1", "y2"],
        )
        schema = ds.schema()
        assert len(schema["vdims"]) == 2
        assert schema["vdims"][0]["name"] == "y1"
        assert schema["vdims"][1]["name"] == "y2"

    def test_schema_on_curve_element(self):
        hv.Curve.datatype = ["dictionary"]
        try:
            curve = hv.Curve({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
            schema = curve.schema()
            assert len(schema["kdims"]) == 1
            assert len(schema["vdims"]) == 1
            assert schema["kdims"][0]["name"] == "x"
            assert schema["vdims"][0]["name"] == "y"
        finally:
            hv.Curve.datatype = self.restore_datatype

    def test_schema_on_table_element(self):
        hv.Table.datatype = ["dictionary"]
        try:
            table = hv.Table({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}, kdims=["x"], vdims=["y"])
            schema = table.schema()
            assert len(schema["kdims"]) == 1
            assert len(schema["vdims"]) == 1
        finally:
            hv.Table.datatype = self.restore_datatype


class TestDatasetSchemaPandas:
    def setup_method(self):
        pd = pytest.importorskip("pandas")
        self.pd = pd
        self.restore_datatype = hv.Dataset.datatype
        hv.Dataset.datatype = ["dataframe"]

    def teardown_method(self):
        hv.Dataset.datatype = self.restore_datatype

    def test_schema_basic_structure(self):
        df = self.pd.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        schema = ds.schema()
        assert "kdims" in schema
        assert "vdims" in schema

    def test_schema_kdim_fields(self):
        df = self.pd.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        _assert_schema_fields(kdim_schema)
        assert kdim_schema["name"] == "x"
        assert "int" in kdim_schema["dtype"]
        assert kdim_schema["is_categorical"] == False
        assert kdim_schema["unique_count"] == 3
        assert kdim_schema["missing_count"] == 0

    def test_schema_vdim_fields(self):
        df = self.pd.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        vdim_schema = ds.schema()["vdims"][0]
        _assert_schema_fields(vdim_schema)
        assert vdim_schema["name"] == "y"
        assert "float" in vdim_schema["dtype"]
        assert kdim_schema["is_nullable"] == True
        assert vdim_schema["range"] == (4.0, 6.0)

    def test_schema_missing_values(self):
        df = self.pd.DataFrame({"x": [1, 2, 3], "y": [4.0, float("nan"), 6.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        vdim_schema = ds.schema()["vdims"][0]
        assert vdim_schema["missing_count"] == 1

    def test_schema_categorical(self):
        df = self.pd.DataFrame({"cat": ["a", "b", "c"], "val": [1, 2, 3]})
        ds = hv.Dataset(df, kdims=["cat"], vdims=["val"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["is_categorical"] == True

    def test_schema_datetime(self):
        df = self.pd.DataFrame(
            {"t": self.pd.date_range("2023-01-01", periods=3), "val": [1, 2, 3]}
        )
        ds = hv.Dataset(df, kdims=["t"], vdims=["val"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["is_datetime"] == True

    def test_schema_nullable_int_with_nan(self):
        df = self.pd.DataFrame({"x": self.pd.array([1, 2, None], dtype="Int64"), "y": [4, 5, 6]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["missing_count"] == 1
        assert kdim_schema["is_nullable"] == True

    def test_schema_unique_count(self):
        df = self.pd.DataFrame({"x": [1, 1, 2, 3], "y": [4.0, 5.0, 6.0, 7.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["unique_count"] == 3


class TestDatasetSchemaDask:
    def setup_method(self):
        dd = pytest.importorskip("dask.dataframe")
        pd = pytest.importorskip("pandas")
        self.dd = dd
        self.pd = pd
        self.restore_datatype = hv.Dataset.datatype
        hv.Dataset.datatype = ["dask"]

    def teardown_method(self):
        hv.Dataset.datatype = self.restore_datatype

    def test_schema_basic_structure(self):
        df = self.pd.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
        ddf = self.dd.from_pandas(df, npartitions=1)
        ds = hv.Dataset(ddf, kdims=["x"], vdims=["y"])
        schema = ds.schema()
        assert "kdims" in schema
        assert "vdims" in schema

    def test_schema_missing_values(self):
        df = self.pd.DataFrame({"x": [1, 2, 3], "y": [4.0, float("nan"), 6.0]})
        ddf = self.dd.from_pandas(df, npartitions=1)
        ds = hv.Dataset(ddf, kdims=["x"], vdims=["y"])
        vdim_schema = ds.schema()["vdims"][0]
        assert vdim_schema["missing_count"] == 1

    def test_schema_unique_count(self):
        df = self.pd.DataFrame({"x": [1, 1, 2, 3], "y": [4.0, 5.0, 6.0, 7.0]})
        ddf = self.dd.from_pandas(df, npartitions=1)
        ds = hv.Dataset(ddf, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["unique_count"] == 3


class TestDatasetSchemaXArray:
    def setup_method(self):
        xr = pytest.importorskip("xarray")
        self.xr = xr
        self.restore_datatype = hv.Dataset.datatype
        hv.Dataset.datatype = ["xarray"]

    def teardown_method(self):
        hv.Dataset.datatype = self.restore_datatype

    def test_schema_basic_structure(self):
        ds_xr = self.xr.Dataset(
            {"temp": (["x", "y"], np.array([[1.0, 2.0], [3.0, 4.0]]))},
            coords={"x": [0, 1], "y": [0, 1]},
        )
        ds = hv.Dataset(ds_xr, kdims=["x", "y"], vdims=["temp"])
        schema = ds.schema()
        assert "kdims" in schema
        assert "vdims" in schema
        assert len(schema["kdims"]) == 2
        assert len(schema["vdims"]) == 1

    def test_schema_range(self):
        ds_xr = self.xr.Dataset(
            {"temp": (["x", "y"], np.array([[1.0, 2.0], [3.0, 4.0]]))},
            coords={"x": [0, 1], "y": [10, 20]},
        )
        ds = hv.Dataset(ds_xr, kdims=["x", "y"], vdims=["temp"])
        vdim_schema = ds.schema()["vdims"][0]
        assert vdim_schema["range"] == (1.0, 4.0)

    def test_schema_missing_values(self):
        data = np.array([[1.0, float("nan")], [3.0, 4.0]])
        ds_xr = self.xr.Dataset(
            {"temp": (["x", "y"], data)},
            coords={"x": [0, 1], "y": [0, 1]},
        )
        ds = hv.Dataset(ds_xr, kdims=["x", "y"], vdims=["temp"])
        vdim_schema = ds.schema()["vdims"][0]
        assert vdim_schema["missing_count"] == 1


class TestDatasetSchemaNarwhalsPandas:
    def setup_method(self):
        nw = pytest.importorskip("narwhals.stable.v2")
        pd = pytest.importorskip("pandas")
        self.nw = nw
        self.pd = pd
        self.restore_datatype = hv.Dataset.datatype
        hv.Dataset.datatype = ["narwhals"]

    def teardown_method(self):
        hv.Dataset.datatype = self.restore_datatype

    def test_schema_basic_structure(self):
        df = self.pd.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        schema = ds.schema()
        assert "kdims" in schema
        assert "vdims" in schema

    def test_schema_missing_values(self):
        df = self.pd.DataFrame({"x": [1, 2, 3], "y": [4.0, float("nan"), 6.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        vdim_schema = ds.schema()["vdims"][0]
        assert vdim_schema["missing_count"] == 1

    def test_schema_unique_count(self):
        df = self.pd.DataFrame({"x": [1, 1, 2, 3], "y": [4.0, 5.0, 6.0, 7.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["unique_count"] == 3

    def test_schema_categorical(self):
        df = self.pd.DataFrame({"cat": ["a", "b", "c"], "val": [1, 2, 3]})
        ds = hv.Dataset(df, kdims=["cat"], vdims=["val"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["is_categorical"] == True


class TestDatasetSchemaNarwhalsPolars:
    def setup_method(self):
        pl = pytest.importorskip("polars")
        self.pl = pl
        self.restore_datatype = hv.Dataset.datatype
        hv.Dataset.datatype = ["narwhals"]

    def teardown_method(self):
        hv.Dataset.datatype = self.restore_datatype

    def test_schema_basic_structure(self):
        df = self.pl.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        schema = ds.schema()
        assert "kdims" in schema
        assert "vdims" in schema

    def test_schema_missing_values(self):
        df = self.pl.DataFrame({"x": [1, 2, 3], "y": [4.0, None, 6.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        vdim_schema = ds.schema()["vdims"][0]
        assert vdim_schema["missing_count"] == 1

    def test_schema_unique_count(self):
        df = self.pl.DataFrame({"x": [1, 1, 2, 3], "y": [4.0, 5.0, 6.0, 7.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["unique_count"] == 3


class TestDatasetSchemaCrossInterfaceConsistency:
    """Verify that schema fields are consistent across pandas and narwhals backends."""

    def test_pandas_narwhals_same_fields(self):
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
        restore = hv.Dataset.datatype

        hv.Dataset.datatype = ["dataframe"]
        ds_pd = hv.Dataset(df, kdims=["x"], vdims=["y"])
        schema_pd = ds_pd.schema()

        hv.Dataset.datatype = ["narwhals"]
        ds_nw = hv.Dataset(df, kdims=["x"], vdims=["y"])
        schema_nw = ds_nw.schema()

        hv.Dataset.datatype = restore

        for role in ("kdims", "vdims"):
            for pd_entry, nw_entry in zip(schema_pd[role], schema_nw[role]):
                assert set(pd_entry.keys()) == set(nw_entry.keys()) == _SCHEMA_FIELDS
                assert pd_entry["name"] == nw_entry["name"]
                assert pd_entry["is_categorical"] == nw_entry["is_categorical"]
                assert pd_entry["is_datetime"] == nw_entry["is_datetime"]
                assert pd_entry["missing_count"] == nw_entry["missing_count"]
