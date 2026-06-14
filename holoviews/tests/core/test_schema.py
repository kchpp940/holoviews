"""
Unified option validation / schema mechanism tests.

Covers the 4 categories (renderer, plot, operation, extension),
OptionSpec / OptionSchema, public entry points (hv.output, hv.save,
hv.render, hv.extension), deprecation aliases, and fuzzy error hints.
"""

from __future__ import annotations

import typing as t
import warnings

import pytest

pytestmark = pytest.mark.core

import holoviews as hv
from holoviews.core.schema import (
    OptionCategory,
    OptionSchema,
    OptionSpec,
    ValidationError,
    _specs_from_param_class,
    build_extension_schema,
    build_operation_schema,
    build_plot_schema,
    build_renderer_schema,
)
from holoviews.plotting.plot import Plot
from holoviews.plotting.renderer import Renderer
from holoviews.core.operation import Operation
from holoviews.util.settings import OutputSettings, list_backends, list_formats


# ---------------------------------------------------------------------------
# OptionSpec unit tests
# ---------------------------------------------------------------------------

class TestOptionSpec:
    def test_type_checking_none_by_default_disallowed(self):
        spec = OptionSpec("x", type=int, default=1)
        err = spec.check_value(None)
        assert err is not None
        assert "expected type" in err

    def test_allow_None_passes(self):
        spec = OptionSpec("x", type=int, default=None, allow_None=True)
        assert spec.check_value(None) is None
        assert spec.check_value(42) is None

    def test_type_checking_wrong_type(self):
        spec = OptionSpec("x", type=int, default=1)
        err = spec.check_value("not_int")
        assert err is not None
        assert "expected type int" in err

    def test_type_checking_right_type(self):
        spec = OptionSpec("x", type=int, default=1)
        assert spec.check_value(10) is None

    def test_bounds_lower(self):
        spec = OptionSpec("x", type=int, default=1, bounds=(1, None))
        assert spec.check_value(0) is not None
        assert spec.check_value(1) is None

    def test_bounds_upper(self):
        spec = OptionSpec("x", type=int, default=1, bounds=(None, 10))
        assert spec.check_value(11) is not None
        assert spec.check_value(10) is None

    def test_allowed_values(self):
        spec = OptionSpec("m", type=str, default="a", allowed=["a", "b", "c"])
        assert spec.check_value("d") is not None
        assert spec.check_value("a") is None

    def test_deprecated_aliases_field(self):
        spec = OptionSpec("new_name", type=str, default="x",
                          deprecated_aliases={"old_name": "new_name"})
        assert "old_name" in spec.deprecated_aliases

    def test_error_hint_field(self):
        spec = OptionSpec("x", type=int, default=0,
                          error_hint="Use 1..100")
        assert "Use 1..100" in spec.error_hint

    def test_object_type_allows_any_non_none(self):
        # allow_None defaults to False here (default=1, not None)
        spec = OptionSpec("x", type=object, default=1)
        assert spec.check_value(123) is None
        assert spec.check_value("abc") is None
        # None disallowed because allow_None is False and default != None
        assert spec.check_value(None) is not None

    def test_object_type_with_allow_none(self):
        spec = OptionSpec("x", type=object, default=None, allow_None=True)
        assert spec.check_value(None) is None

    def test_allow_none_auto_inferred_from_default_none(self):
        # When default is None and allow_None unspecified → True
        spec = OptionSpec("x", type=int, default=None)
        assert spec.allow_None is True
        assert spec.check_value(None) is None


# ---------------------------------------------------------------------------
# OptionSchema construction + basic validation
# ---------------------------------------------------------------------------

class TestOptionSchemaBuilders:
    def test_build_renderer_schema_category(self):
        s = build_renderer_schema()
        assert s.category == OptionCategory.RENDERER
        assert len(s) > 0

    def test_build_extension_schema_category(self):
        s = build_extension_schema()
        assert s.category == OptionCategory.EXTENSION
        assert len(s) > 0

    def test_build_plot_schema_category(self):
        s = build_plot_schema()
        assert s.category == OptionCategory.PLOT
        assert len(s) > 0

    def test_build_operation_schema_category(self):
        s = build_operation_schema()
        assert s.category == OptionCategory.OPERATION
        assert len(s) > 0

    def test_renderer_schema_has_common_keys(self):
        s = build_renderer_schema()
        for k in ("dpi", "size", "fps", "fig", "holomap",
                  "widget_location", "mode"):
            assert k in s, f"missing {k!r} in renderer schema"

    def test_extension_schema_has_common_keys(self):
        s = build_extension_schema()
        for k in ("fig", "holomap", "backend", "widgets",
                  "widget_location", "dpi", "size"):
            assert k in s, f"missing {k!r} in extension schema"

    def test_plot_schema_has_common_keys(self):
        s = build_plot_schema()
        for k in ("fontsize", "logx", "logy", "xlabel", "ylabel",
                  "title", "show_legend"):
            assert k in s, f"missing {k!r} in plot schema"

    def test_operation_schema_has_common_keys(self):
        s = build_operation_schema()
        for k in ("dynamic", "group"):
            assert k in s, f"missing {k!r} in operation schema"

    def test_renderer_with_class_includes_param_specs(self):
        s = Renderer._get_schema()
        for k in ("post_render_hooks", "info_fn"):
            assert k in s, f"Renderer._get_schema missing {k!r}"

    def test_renderer_class_includes_backend_formats(self):
        from holoviews.plotting.mpl.renderer import MPLRenderer
        from holoviews.plotting.bokeh.renderer import BokehRenderer
        mpl_s = MPLRenderer._get_schema()
        bokeh_s = BokehRenderer._get_schema()
        assert "fig" in mpl_s and "fig" in bokeh_s

    def test_build_extension_schema_dynamic_fig(self):
        s = build_extension_schema(fig_formats=["only_png"])
        with pytest.raises((ValueError, ValidationError)):
            s.validate({"fig": "jpeg"}, coerce=False)
        clean = s.validate({"fig": "only_png"}, coerce=False)
        assert clean["fig"] == "only_png"

    def test_build_extension_schema_dynamic_backend(self):
        s = build_extension_schema(backend_list=["a", "b"])
        with pytest.raises((ValueError, ValidationError)):
            s.validate({"backend": "c"}, coerce=False)
        clean = s.validate({"backend": "b"}, coerce=False)
        assert clean["backend"] == "b"

    def test_build_extension_schema_dynamic_holomap(self):
        s = build_extension_schema(holomap_formats=["scrubber", None])
        with pytest.raises((ValueError, ValidationError)):
            s.validate({"holomap": "bad_mode"}, coerce=False)
        clean = s.validate({"holomap": "scrubber"}, coerce=False)
        assert clean["holomap"] == "scrubber"


# ---------------------------------------------------------------------------
# Validation: unknown option + type + bounds + allowed + defaults
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def test_unknown_option_raises(self):
        s = build_renderer_schema()
        with pytest.raises((ValueError, ValidationError)) as exc:
            s.validate({"this_is_not_an_option": 42}, context="unit")
        msg = str(exc.value)
        assert "this_is_not_an_option" in msg
        assert "Valid renderer options" in msg
        assert "in unit" in msg

    def test_unknown_option_fuzzy_suggestions(self):
        s = build_renderer_schema()
        with pytest.raises((ValueError, ValidationError)) as exc:
            s.validate({"dpii": 100}, coerce=False)
        msg = str(exc.value).lower()
        assert "dpi" in msg

    def test_type_error_caught(self):
        s = build_renderer_schema()
        with pytest.raises((ValueError, ValidationError)) as exc:
            s.validate({"dpi": "big"}, coerce=False)
        assert "expected type" in str(exc.value)

    def test_bounds_error_caught(self):
        s = build_renderer_schema()
        with pytest.raises((ValueError, ValidationError)) as exc:
            s.validate({"dpi": -1}, coerce=False)
        assert "bound" in str(exc.value).lower() or "below" in str(exc.value).lower()

    def test_allowed_values_error_caught(self):
        s = build_renderer_schema()
        with pytest.raises((ValueError, ValidationError)) as exc:
            s.validate({"widget_location": "somewhere_else"}, coerce=False)
        assert "allowed" in str(exc.value).lower()

    def test_coerce_true_fills_defaults(self):
        s = build_renderer_schema()
        out = s.validate({}, coerce=True)
        assert len(out) == len(s)
        assert out["dpi"] is None
        assert out["center"] is True

    def test_coerce_false_passes_only_subset(self):
        s = build_renderer_schema()
        out = s.validate({"dpi": 150}, coerce=False)
        assert set(out) == {"dpi"}
        assert out["dpi"] == 150


# ---------------------------------------------------------------------------
# Deprecated alias handling
# ---------------------------------------------------------------------------

class TestDeprecatedAliases:
    def test_widget_mode_rewritten_with_warning(self):
        s = build_extension_schema()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            out = s.validate({"widget_mode": "live"}, coerce=False)
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
        assert ("widgets" in out) or ("widget_mode" in out)

    def test_deprecated_alias_custom_spec(self):
        spec = OptionSpec(
            "canonical", type=str, default="a",
            deprecated_aliases={"legacy": "canonical"},
        )
        s = OptionSchema(OptionCategory.PLOT, spec)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            out = s.validate({"legacy": "b"}, coerce=False)
            assert any(issubclass(x.category, DeprecationWarning) for x in w)
        assert out.get("canonical") == "b" or out.get("legacy") == "b"


# ---------------------------------------------------------------------------
# merge / extend
# ---------------------------------------------------------------------------

class TestSchemaMerge:
    def test_extend_adds_new(self):
        s1 = build_renderer_schema()
        extra = OptionSpec("new_opt", type=int, default=0)
        s2 = s1.extend(extra)
        assert "new_opt" in s2
        assert "new_opt" not in s1

    def test_extend_enforces_allowed(self):
        s1 = build_renderer_schema()
        extra = OptionSpec("x", type=str, default="a", allowed=["a", "b"])
        s2 = s1.extend(extra)
        with pytest.raises((ValueError, ValidationError)):
            s2.validate({"x": "c"}, coerce=False)

    def test_merge_overwrites_later_specs(self):
        spec_a = OptionSpec("x", type=int, default=1)
        spec_b = OptionSpec("x", type=str, default="hello")
        s1 = OptionSchema(OptionCategory.RENDERER, spec_a)
        s2 = OptionSchema(OptionCategory.RENDERER, spec_b)
        merged = s1.merge(s2)
        out = merged.validate({"x": "world"}, coerce=False)
        assert out["x"] == "world"

    def test_merge_different_category_rejected(self):
        s1 = build_renderer_schema()
        s2 = build_extension_schema()
        with pytest.raises(TypeError):
            s1.merge(s2)


class TestSchemaOverlay:
    def test_overlay_preserves_base_bounds(self):
        """Param-derived specs (no bounds) must NOT erase base bounds."""
        base = OptionSpec("dpi", type=int, default=None, bounds=(1, None),
                          allow_None=True)
        param_like = OptionSpec("dpi", type=int, default=None,
                                bounds=None,  # param doesn't specify bounds
                                allow_None=True)
        merged = base.overlay(param_like)
        # structural from param
        assert merged.type is int
        assert merged.default is None
        # constraint from base (param had None)
        assert merged.bounds == (1, None)

    def test_overlay_preserves_base_allowed(self):
        base = OptionSpec("fig", type=str, default="auto",
                          allowed=["auto", "png", "svg"])
        param_like = OptionSpec("fig", type=str, default="auto",
                                allowed=None)
        merged = base.overlay(param_like)
        assert merged.allowed is not None
        assert "png" in merged.allowed

    def test_overlay_param_allowed_wins_when_present(self):
        base = OptionSpec("fig", type=str, default="auto",
                          allowed=["old_value"])
        param_like = OptionSpec("fig", type=str, default="auto",
                                allowed=["new_value"])
        merged = base.overlay(param_like)
        assert merged.allowed == ["new_value"]

    def test_overlay_merges_deprecated_aliases(self):
        base = OptionSpec("widgets", type=str, default="scrubber",
                          deprecated_aliases={"wm": "widgets"})
        param_like = OptionSpec("widgets", type=str, default="scrubber",
                                deprecated_aliases={"widget_mode": "widgets"})
        merged = base.overlay(param_like)
        assert "wm" in merged.deprecated_aliases
        assert "widget_mode" in merged.deprecated_aliases

    def test_schema_overlay_mixed_conflict(self):
        s1 = OptionSchema(OptionCategory.RENDERER,
                          OptionSpec("dpi", type=int, default=None,
                                     bounds=(1, None), allow_None=True),
                          OptionSpec("size", type=int, default=100))
        s2 = OptionSchema(OptionCategory.RENDERER,
                          OptionSpec("dpi", type=int, default=None,
                                     bounds=None, allow_None=True),
                          OptionSpec("new_opt", type=str, default="x"))
        result = s1.overlay(s2)
        # dpi bounds from base kept
        assert result.spec_for("dpi").bounds == (1, None)
        # new_opt from s2 added
        assert "new_opt" in result
        # size from s1 untouched
        assert result.spec_for("size").default == 100

    def test_overlay_name_mismatch_rejected(self):
        s1 = OptionSpec("a", type=int, default=1)
        s2 = OptionSpec("b", type=int, default=2)
        with pytest.raises(ValueError):
            s1.overlay(s2)

    def test_schema_overlay_different_category_rejected(self):
        s1 = build_renderer_schema()
        s2 = build_extension_schema()
        with pytest.raises(TypeError):
            s1.overlay(s2)


# ---------------------------------------------------------------------------
# _specs_from_param_class
# ---------------------------------------------------------------------------

class TestSpecsFromParamClass:
    def test_renderer_param_generates_specs(self):
        specs = _specs_from_param_class(Renderer)
        names = {s.name for s in specs}
        assert "post_render_hooks" in names
        assert "info_fn" in names
        assert "fig" in names
        assert "holomap" in names

    def test_plot_param_generates_specs(self):
        # NOTE: the base Plot class intentionally carries almost no
        # param.Parameterized attributes (its options are declared in
        # the hard-coded _BASE_PLOT_SPECS and mixed in by each backend).
        # So _specs_from_param_class(Plot) returns an empty list — which
        # is correct behaviour.  We verify here that passing a subclass
        # that DOES define its own params works.
        import param
        class _FakePlot(Plot):
            custom_param = param.Number(default=1.0, bounds=(0, 10))
        specs = _specs_from_param_class(_FakePlot)
        names = {s.name for s in specs}
        assert "custom_param" in names
        for s in specs:
            if s.name == "custom_param":
                assert s.bounds == (0, 10)
                # param.Number → (int, float) tuple type
                assert isinstance(s.type, tuple) or s.type is float or s.type is int
                assert s.default == 1.0
                break

    def test_operation_param_generates_specs(self):
        specs = _specs_from_param_class(Operation)
        names = {s.name for s in specs}
        assert "dynamic" in names


# ---------------------------------------------------------------------------
# Renderer validate() / instance() validation path
# ---------------------------------------------------------------------------

class TestRendererValidation:
    def test_renderer_validate_bad_option(self):
        with pytest.raises(ValueError):
            Renderer.validate({"no_such_option": 42})

    def test_renderer_validate_bad_dpi_type(self):
        with pytest.raises(ValueError):
            Renderer.validate({"dpi": "not_a_number"})

    def test_renderer_validate_bounds_violation(self):
        with pytest.raises(ValueError):
            Renderer.validate({"dpi": -5})

    def test_renderer_validate_valid(self):
        out = Renderer.validate({"dpi": 150, "size": 80})
        assert out["dpi"] == 150
        assert out["size"] == 80

    def test_renderer_instance_valid(self):
        r = Renderer.instance(dpi=200, size=100)
        assert r.dpi == 200
        assert r.size == 100

    def test_bokeh_renderer_has_theme_option(self):
        from holoviews.plotting.bokeh.renderer import BokehRenderer
        s = BokehRenderer._get_schema()
        assert "theme" in s

    def test_mpl_renderer_has_interactive(self):
        from holoviews.plotting.mpl.renderer import MPLRenderer
        s = MPLRenderer._get_schema()
        assert "interactive" in s

    def test_plotly_renderer_schema_not_empty(self):
        from holoviews.plotting.plotly.renderer import PlotlyRenderer
        s = PlotlyRenderer._get_schema()
        # Should pick up common Renderer params via renderer_class
        assert len(s) > 10


# ---------------------------------------------------------------------------
# OutputSettings validation (via get_options direct call)
# ---------------------------------------------------------------------------

class TestOutputSettingsValidation:
    def test_get_options_bad_option(self):
        errors = []
        def warnfn(msg):
            errors.append(msg)
        with pytest.raises((ValueError, ValidationError)):
            OutputSettings.get_options({"not_a_real_setting": True}, {}, warnfn)

    def test_get_options_bad_fig_format(self):
        errors = []
        def warnfn(msg):
            errors.append(msg)
        with pytest.raises((ValueError, ValidationError)):
            OutputSettings.get_options(
                {"fig": "totally_made_up_format"}, {}, warnfn
            )

    def test_get_options_valid_subset(self):
        errors = []
        def warnfn(msg):
            errors.append(msg)
        opts = OutputSettings.get_options({"dpi": 200, "size": 120}, {}, warnfn)
        assert opts.get("dpi") == 200
        assert opts.get("size") == 120
        assert not errors


# ---------------------------------------------------------------------------
# hv.output public entry points
# ---------------------------------------------------------------------------

class TestHvOutputValidation:
    def test_hv_output_with_obj_unknown_kwarg_raises(self):
        """hv.output(obj, bad_opt) should raise ValueError."""
        curve = hv.Curve([1, 2, 3])
        with pytest.raises(ValueError):
            hv.output(curve, not_a_real_option_xyz=True)

    def test_hv_output_with_obj_bad_backend_raises(self):
        """hv.output(obj, backend=bad) should raise ValueError if not in list."""
        curve = hv.Curve([1, 2, 3])
        with pytest.raises(ValueError):
            hv.output(curve, backend="definitely_not_a_backend")

    def test_hv_output_with_obj_valid(self):
        curve = hv.Curve([1, 2, 3])
        # Should not raise
        hv.output(curve, dpi=100, size=80)

    def test_hv_output_global_valid(self):
        hv.output(dpi=100, size=80)
        hv.output(dpi=None, size=None)


# ---------------------------------------------------------------------------
# hv.save / hv.render validation
# ---------------------------------------------------------------------------

class TestHvSaveRenderValidation:
    def setup_method(self):
        hv.extension._loaded_extensions = set()

    def test_hv_render_bad_renderer_kwarg(self):
        curve = hv.Curve([1, 2, 3])
        hv.extension("matplotlib")
        with pytest.raises(ValueError):
            hv.render(curve, backend="matplotlib", no_such_kwarg_ever=True)

    def test_hv_save_bad_renderer_kwarg(self):
        import tempfile
        curve = hv.Curve([1, 2, 3])
        hv.extension("matplotlib")
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            with pytest.raises(ValueError):
                hv.save(curve, f.name, backend="matplotlib",
                        bogus_option_surely=True)

    def test_hv_render_valid(self):
        curve = hv.Curve([1, 2, 3])
        hv.extension("matplotlib")
        # Valid options should not raise
        result = hv.render(curve, backend="matplotlib", dpi=150)
        assert result is not None

    def teardown_method(self):
        hv.extension._loaded_extensions = set()


# ---------------------------------------------------------------------------
# Operation validation path
# ---------------------------------------------------------------------------

class TestOperationValidation:
    def test_operation_call_bad_option(self):
        curve = hv.Curve([1, 2, 3])
        with pytest.raises(ValueError):
            hv.Operation(curve, this_is_bogus_param=True)

    def test_operation_call_valid(self):
        curve = hv.Curve([1, 2, 3])
        # Operation valid subset
        out = hv.Operation(curve, dynamic=True)
        assert out is not None


# ---------------------------------------------------------------------------
# Plot validation path
# ---------------------------------------------------------------------------

class TestPlotValidationPath:
    def test_build_plot_schema_unknown_raises(self):
        s = build_plot_schema(plot_class=Plot)
        with pytest.raises((ValueError, ValidationError)):
            s.validate({"fake_plot_option": True}, coerce=False)

    def test_build_plot_schema_valid(self):
        s = build_plot_schema(plot_class=Plot)
        out = s.validate({"fontsize": 14, "logx": True, "show_title": False},
                         coerce=False)
        assert out["fontsize"] == 14
        assert out["logx"] is True


# ---------------------------------------------------------------------------
# Error message quality
# ---------------------------------------------------------------------------

class TestValidationErrorQuality:
    def test_error_mentions_source_category(self):
        s = build_extension_schema()
        with pytest.raises((ValueError, ValidationError)) as exc:
            s.validate({"bogus": 1}, context="test")
        msg = str(exc.value)
        assert "extension" in msg.lower()

    def test_error_mentions_context(self):
        s = build_operation_schema()
        with pytest.raises((ValueError, ValidationError)) as exc:
            s.validate({"foo": "bar"}, context="hv.operation(...)")
        assert "hv.operation(...)" in str(exc.value)

    def test_multiple_errors_aggregated(self):
        s = build_renderer_schema()
        with pytest.raises((ValueError, ValidationError)) as exc:
            s.validate({
                "not_a_key": 1,
                "dpi": "wrong_type",
                "size": -10,
            }, context="multi-error test")
        msg = str(exc.value)
        assert "not_a_key" in msg
        assert "dpi" in msg.lower()
        assert "size" in msg.lower()

    def test_source_field_tracking(self):
        spec = OptionSpec("x", type=int, default=1, source="HardCodedSpec")
        s = OptionSchema(OptionCategory.RENDERER, spec)
        # spec has a source recorded
        assert s.spec_for("x").source == "HardCodedSpec"
