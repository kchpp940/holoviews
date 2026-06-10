from __future__ import annotations

import datetime

import numpy as np
import pytest

import holoviews as hv


_BASE_FIELDS = frozenset(
    {"name", "dtype", "is_categorical", "is_datetime", "is_nullable",
     "range", "unique_count", "missing_count", "total_count"}
)

_STATS_KEYS = frozenset(
    {"value", "computed", "estimated", "sample_size", "total_count"}
)


def _assert_schema_fields(schema_entry):
    missing = _BASE_FIELDS - set(schema_entry)
    assert not missing, f"Schema entry missing fields: {missing}"
    for stat in ("range", "unique_count", "missing_count", "total_count"):
        missing = _STATS_KEYS - set(schema_entry[stat])
        assert not missing, f"Stat '{stat}' missing keys: {missing}"


def _stats(stat):
    """Extract the raw value from a stats dict.  Returns ``stat["value"]`` if *stat* is a
    dict with a ``value`` key; otherwise returns *stat* itself.
    """
    if isinstance(stat, dict) and "value" in stat:
        return stat["value"]
    return stat


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

    def test_schema_stats_shape(self):
        ds = hv.Dataset({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        _assert_schema_fields(kdim_schema)

        assert kdim_schema["name"] == "x"
        assert "int" in kdim_schema["dtype"]
        assert kdim_schema["is_categorical"] == False
        assert kdim_schema["is_datetime"] == False
        assert kdim_schema["is_nullable"] == False

        assert kdim_schema["range"]["value"] == (1, 3)
        assert kdim_schema["range"]["computed"] == True
        assert kdim_schema["range"]["estimated"] == False
        assert kdim_schema["range"]["sample_size"] is None

        assert kdim_schema["unique_count"]["value"] == 3
        assert kdim_schema["unique_count"]["computed"] == True
        assert kdim_schema["unique_count"]["estimated"] == False

        assert kdim_schema["missing_count"]["value"] == 0
        assert kdim_schema["missing_count"]["computed"] == True

        assert kdim_schema["total_count"]["value"] == 3
        assert kdim_schema["total_count"]["computed"] == True

    def test_schema_vdim_fields(self):
        ds = hv.Dataset({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}, kdims=["x"], vdims=["y"])
        vdim_schema = ds.schema()["vdims"][0]
        _assert_schema_fields(vdim_schema)

        assert vdim_schema["name"] == "y"
        assert "float" in vdim_schema["dtype"]
        assert vdim_schema["is_nullable"] == True

        assert vdim_schema["range"]["value"] == (4.0, 6.0)
        assert vdim_schema["range"]["computed"] == True
        assert vdim_schema["unique_count"]["value"] == 3
        assert vdim_schema["missing_count"]["value"] == 0
        assert vdim_schema["total_count"]["value"] == 3

    def test_schema_missing_values_float(self):
        ds = hv.Dataset(
            {"x": [1, 2, 3], "y": [4.0, float("nan"), 6.0]}, kdims=["x"], vdims=["y"])
        vdim = ds.schema()["vdims"][0]
        assert vdim["missing_count"]["value"] == 1
        assert vdim["missing_count"]["computed"] == True
        assert vdim["missing_count"]["estimated"] == False

    def test_schema_range(self):
        ds = hv.Dataset({"x": [10, 20, 30], "y": [1.0, 2.0, 3.0]}, kdims=["x"], vdims=["y"])
        assert ds.schema()["kdims"][0]["range"]["value"] == (10, 30)

    def test_schema_unique_count(self):
        ds = hv.Dataset({"x": [1, 1, 2, 3], "y": [4.0, 5.0, 6.0, 7.0]}, kdims=["x"], vdims=["y"])
        assert ds.schema()["kdims"][0]["unique_count"]["value"] == 3

    def test_schema_categorical(self):
        ds = hv.Dataset({"cat": ["a", "b", "c"], "val": [1, 2, 3]}, kdims=["cat"], vdims=["val"])
        kdim = ds.schema()["kdims"][0]
        assert kdim["is_categorical"] == True
        assert kdim["is_datetime"] == False

    def test_schema_datetime(self):
        dates = np.array(["2023-01-01", "2023-01-02", "2023-01-03"], dtype="datetime64[ns]")
        ds = hv.Dataset({"t": dates, "val": [1, 2, 3]}, kdims=["t"], vdims=["val"])
        kdim = ds.schema()["kdims"][0]
        assert kdim["is_datetime"] == True
        assert kdim["is_categorical"] == False

    def test_schema_nullable_float(self):
        ds = hv.Dataset({"x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0]}, kdims=["x"], vdims=["y"])
        assert ds.schema()["kdims"][0]["is_nullable"] == True

    def test_schema_non_nullable_int(self):
        ds = hv.Dataset({"x": [1, 2, 3], "y": [4, 5, 6]}, kdims=["x"], vdims=["y"])
        assert ds.schema()["kdims"][0]["is_nullable"] == False

    def test_schema_is_nullable_structural_only(self):
        """is_nullable must NOT depend on whether missing values exist; must be
        stable across compute/sample_size."""
        ds_no = hv.Dataset({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}, kdims=["x"], vdims=["y"])
        ds_yes = hv.Dataset({"x": [1, 2, 3], "y": [4.0, float("nan"), 6.0]}, kdims=["x"], vdims=["y"])
        assert ds_no.schema()["vdims"][0]["is_nullable"] == True
        assert ds_yes.schema()["vdims"][0]["is_nullable"] == True
        assert ds_yes.schema()["kdims"][0]["is_nullable"] == False
        assert ds_yes.schema(compute=False)["vdims"][0]["is_nullable"] == True
        assert ds_yes.schema(sample_size=2)["vdims"][0]["is_nullable"] == True

    def test_schema_multiple_vdims(self):
        ds = hv.Dataset(
            {"x": [1, 2, 3], "y1": [4.0, 5.0, 6.0], "y2": [7.0, 8.0, 9.0]},
            kdims=["x"], vdims=["y1", "y2"])
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


class TestSchemaMetadataGranularity:
    """Verify per-statistic independent provenance.

    Tests that the coarse dimension-level flags no longer cover all fields, but
    instead each stats object carries its own per-field provenance.  This
    means, for example, that with ``sample_size`` only ``unique_count`` and
    ``missing_count`` are estimated, while ``range`` and ``total_count``
    remain exact.

    """

    def setup_method(self):
        self.restore_datatype = hv.Dataset.datatype
        hv.Dataset.datatype = ["dictionary"]

    def teardown_method(self):
        hv.Dataset.datatype = self.restore_datatype

    def test_compute_false_all_stats_uncomputed(self):
        ds = hv.Dataset({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}, kdims=["x"], vdims=["y"])
        schema = ds.schema(compute=False)
        for entry in schema["kdims"] + schema["vdims"]:
            assert entry["name"] is not None
            assert entry["dtype"] is not None
            for stat_name in ("range", "unique_count", "missing_count", "total_count"):
                s = entry[stat_name]
                assert s["computed"] == False
                assert s["estimated"] == False
                assert s["sample_size"] is None
                assert s["total_count"] is None
                assert s["value"] is None

    def test_compute_false_base_info_intact(self):
        ds = hv.Dataset({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}, kdims=["x"], vdims=["y"])
        schema = ds.schema(compute=False)
        kdim, vdim = schema["kdims"][0], schema["vdims"][0]
        assert kdim["name"] == "x"
        assert "int" in kdim["dtype"]
        assert kdim["is_categorical"] == False
        assert kdim["is_nullable"] == False
        assert vdim["is_nullable"] == True

    def test_sampling_range_and_total_remain_exact(self):
        """range  and total_count are ALWAYS exact when computed, even under sampling."""
        rng = np.random.default_rng(42)
        n = 10_000
        ds = hv.Dataset({
            "x": rng.integers(0, 100, size=n),
            "y": rng.standard_normal(n),
        }, kdims=["x"], vdims=["y"])
        schema = ds.schema(sample_size=1000)
        for entry in schema["kdims"] + schema["vdims"]:
            assert entry["range"]["computed"] == True
            assert entry["range"]["estimated"] == False
            assert entry["range"]["sample_size"] is None
            assert entry["range"]["total_count"] == n

            assert entry["total_count"]["computed"] == True
            assert entry["total_count"]["estimated"] == False
            assert entry["total_count"]["value"] == n

            assert entry["unique_count"]["computed"] == True
            assert entry["missing_count"]["computed"] == True

    def test_sampling_unique_missing_are_estimated(self):
        rng = np.random.default_rng(42)
        n = 10_000
        ds = hv.Dataset({
            "x": rng.integers(0, 10_000, size=n),
            "y": rng.standard_normal(n),
        }, kdims=["x"], vdims=["y"])
        schema = ds.schema(sample_size=1000)
        for entry in schema["kdims"] + schema["vdims"]:
            # missing_count is always estimated under sampling
            assert entry["missing_count"]["estimated"] == True
            assert entry["missing_count"]["sample_size"] == 1000
        # High-cardinality dims are also estimated
        assert schema["vdims"][0]["unique_count"]["estimated"] == True
        assert schema["vdims"][0]["unique_count"]["sample_size"] == 1000

    def test_sample_size_ge_total_not_estimated(self):
        ds = hv.Dataset({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}, kdims=["x"], vdims=["y"])
        schema = ds.schema(sample_size=10_000)
        for entry in schema["kdims"] + schema["vdims"]:
            for stat in ("range", "unique_count", "missing_count", "total_count"):
                assert entry[stat]["computed"] == True
                assert entry[stat]["estimated"] == False
                assert entry[stat]["sample_size"] is None

    def test_empty_column(self):
        ds = hv.Dataset({"x": [], "y": []}, kdims=["x"], vdims=["y"])
        kdim = ds.schema()["kdims"][0]
        assert kdim["total_count"]["value"] == 0
        assert kdim["range"]["value"] == (None, None)
        assert kdim["unique_count"]["value"] == 0
        assert kdim["missing_count"]["value"] == 0

    def test_all_missing_column(self):
        ds = hv.Dataset(
            {"x": [1, 2, 3], "y": [float("nan"), float("nan"), float("nan")]},
            kdims=["x"], vdims=["y"])
        vdim = ds.schema()["vdims"][0]
        assert vdim["missing_count"]["value"] == vdim["total_count"]["value"] == 3

    def test_no_top_level_provenance_flags(self):
        """provenance must live per-stat, not as bare scalars on the dimension dict."""
        ds = hv.Dataset({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}, kdims=["x"], vdims=["y"])
        schema = ds.schema(sample_size=10_000)
        for entry in schema["kdims"] + schema["vdims"]:
            for key in ("computed", "estimated", "sample_size"):
                assert key not in entry, f"'{key}' should not be a top-level scalar"
            # — dict, not a flat flag.
            for key in ("range", "unique_count", "missing_count", "total_count"):
                assert key in entry and isinstance(entry[key], dict), f"'{key}' should be a top-level stats dict"

    def test_per_stat_independence(self):
        """sanity — each stat has its own provenance."""
        ds = hv.Dataset({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]}, kdims=["x"], vdims=["y"])
        kdim = ds.schema()["kdims"][0]
        assert id(kdim["range"]) != id(kdim["unique_count"])
        assert id(kdim["range"]) != id(kdim["missing_count"])
        assert id(kdim["range"]) != id(kdim["total_count"])


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
        assert kdim_schema["unique_count"]["value"] == 3
        assert kdim_schema["missing_count"]["value"] == 0

    def test_schema_vdim_fields(self):
        df = self.pd.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        vdim_schema = ds.schema()["vdims"][0]
        _assert_schema_fields(vdim_schema)
        assert vdim_schema["name"] == "y"
        assert "float" in vdim_schema["dtype"]
        assert vdim_schema["is_nullable"] == True
        assert vdim_schema["range"]["value"] == (4.0, 6.0)

    def test_schema_missing_values(self):
        df = self.pd.DataFrame({"x": [1, 2, 3], "y": [4.0, float("nan"), 6.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        vdim_schema = ds.schema()["vdims"][0]
        assert vdim_schema["missing_count"]["value"] == 1

    def test_schema_categorical(self):
        df = self.pd.DataFrame({"cat": ["a", "b", "c"], "val": [1, 2, 3]})
        ds = hv.Dataset(df, kdims=["cat"], vdims=["val"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["is_categorical"] == True

    def test_schema_datetime(self):
        df = self.pd.DataFrame(
            {"t": self.pd.date_range("2023-01-01", periods=3), "val": [1, 2, 3]})
        ds = hv.Dataset(df, kdims=["t"], vdims=["val"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["is_datetime"] == True

    def test_schema_nullable_int_with_nan(self):
        df = self.pd.DataFrame({"x": self.pd.array([1, 2, None], dtype="Int64"), "y": [4, 5, 6]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["missing_count"]["value"] == 1
        assert kdim_schema["is_nullable"] == True

    def test_schema_unique_count(self):
        df = self.pd.DataFrame({"x": [1, 1, 2, 3], "y": [4.0, 5.0, 6.0, 7.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["unique_count"]["value"] == 3

    def test_schema_with_sample_size(self):
        rng = np.random.default_rng(42)
        n = 10_000
        df = self.pd.DataFrame({
            "x": rng.integers(0, 10_000, size=n),
            "y": rng.standard_normal(n),
        })
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])

        full_schema = ds.schema()
        sampled_schema = ds.schema(sample_size=1000)

        for role in ("kdims", "vdims"):
            for full_entry, sampled_entry in zip(full_schema[role], sampled_schema[role]):
                assert full_entry["name"] == sampled_entry["name"]
                assert full_entry["dtype"] == sampled_entry["dtype"]
                assert full_entry["is_categorical"] == sampled_entry["is_categorical"]
                assert full_entry["is_datetime"] == sampled_entry["is_datetime"]
                assert full_entry["is_nullable"] == sampled_entry["is_nullable"]

                assert full_entry["range"]["value"] == sampled_entry["range"]["value"]
                assert full_entry["range"]["estimated"] == sampled_entry["range"]["estimated"]
                assert full_entry["range"]["sample_size"] == sampled_entry["range"]["sample_size"]

                assert 0 < sampled_entry["unique_count"]["value"] <= full_entry["unique_count"]["value"]

                # High-cardinality float vdim is estimated; int kdim may or may not be depending on cardinality
                assert sampled_entry["missing_count"]["estimated"] == True
                assert sampled_entry["range"]["estimated"] == False
                assert sampled_entry["total_count"]["estimated"] == False
        # Both dims have high cardinality here, assert both unique_counts estimated
        for role in ("kdims", "vdims"):
            for sampled_entry in sampled_schema[role]:
                assert sampled_entry["unique_count"]["estimated"] == True

    def test_schema_compute_false_pandas(self):
        df = self.pd.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        schema = ds.schema(compute=False)
        for entry in schema["kdims"] + schema["vdims"]:
            for stat_name in ("range", "unique_count", "missing_count", "total_count"):
                s = entry[stat_name]
                assert s["computed"] == False
                assert s["value"] is None
                assert s["estimated"] == False
                assert s["sample_size"] is None
                assert s["total_count"] is None


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
        assert vdim_schema["missing_count"]["value"] == 1

    def test_schema_unique_count(self):
        df = self.pd.DataFrame({"x": [1, 1, 2, 3], "y": [4.0, 5.0, 6.0, 7.0]})
        ddf = self.dd.from_pandas(df, npartitions=1)
        ds = hv.Dataset(ddf, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["unique_count"]["value"] == 3

    def test_schema_compute_false_dask(self):
        df = self.pd.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
        ddf = self.dd.from_pandas(df, npartitions=1)
        ds = hv.Dataset(ddf, kdims=["x"], vdims=["y"])
        schema = ds.schema(compute=False)
        for entry in schema["kdims"] + schema["vdims"]:
            for stat_name in ("range", "unique_count", "missing_count", "total_count"):
                s = entry[stat_name]
                assert s["computed"] == False
                assert s["value"] is None


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
            {"temp": (["x", "y"], np.array([[1.0, 2.0], [3.0, 4.0]])},
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
            {"temp": (["x", "y"], np.array([[1.0, 2.0], [3.0, 4.0]])},
            coords={"x": [0, 1], "y": [10, 20]},
        )
        ds = hv.Dataset(ds_xr, kdims=["x", "y"], vdims=["temp"])
        vdim_schema = ds.schema()["vdims"][0]
        assert vdim_schema["range"]["value"] == (1.0, 4.0)

    def test_schema_missing_values(self):
        data = np.array([[1.0, float("nan")], [3.0, 4.0]])
        ds_xr = self.xr.Dataset(
            {"temp": (["x", "y"], data)},
            coords={"x": [0, 1], "y": [0, 1]},
        )
        ds = hv.Dataset(ds_xr, kdims=["x", "y"], vdims=["temp"])
        vdim_schema = ds.schema()["vdims"][0]
        assert vdim_schema["missing_count"]["value"] == 1


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
        assert vdim_schema["missing_count"]["value"] == 1

    def test_schema_unique_count(self):
        df = self.pd.DataFrame({"x": [1, 1, 2, 3], "y": [4.0, 5.0, 6.0, 7.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["unique_count"]["value"] == 3

    def test_schema_categorical(self):
        df = self.pd.DataFrame({"cat": ["a", "b", "c"], "val": [1, 2, 3]})
        ds = hv.Dataset(df, kdims=["cat"], vdims=["val"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["is_categorical"] == True

    def test_schema_compute_false_narwhals(self):
        df = self.pd.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        schema = ds.schema(compute=False)
        for entry in schema["kdims"] + schema["vdims"]:
            for stat_name in ("range", "unique_count", "missing_count", "total_count"):
                s = entry[stat_name]
                assert s["computed"] == False
                assert s["value"] is None


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
        assert vdim_schema["missing_count"]["value"] == 1

    def test_schema_unique_count(self):
        df = self.pl.DataFrame({"x": [1, 1, 2, 3], "y": [4.0, 5.0, 6.0, 7.0]})
        ds = hv.Dataset(df, kdims=["x"], vdims=["y"])
        kdim_schema = ds.schema()["kdims"][0]
        assert kdim_schema["unique_count"]["value"] == 3


class TestDatasetSchemaCrossInterfaceConsistency:
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
                _assert_schema_fields(pd_entry)
                _assert_schema_fields(nw_entry)
                assert pd_entry["name"] == nw_entry["name"]
                assert pd_entry["is_categorical"] == nw_entry["is_categorical"]
                assert pd_entry["is_datetime"] == nw_entry["is_datetime"]
                assert pd_entry["is_nullable"] == nw_entry["is_nullable"]

                for stat in ("range", "unique_count", "missing_count", "total_count"):
                    for flag in ("computed", "estimated", "sample_size", "total_count"):
                        assert pd_entry[stat][flag] == nw_entry[stat][flag]

                # Compare numeric values
                for stat in ("unique_count", "missing_count", "total_count"):
                    assert pd_entry[stat]["value"] == nw_entry[stat]["value"]

                # Range tuples may have different numpy/narwhals scalar types but compare equal numerically
                pd_rng = pd_entry["range"]["value"]
                nw_rng = nw_entry["range"]["value"]
                assert pd_rng is not None and nw_rng is not None
                for a, b in zip(pd_rng, nw_rng):
                    assert float(a) == float(b)
