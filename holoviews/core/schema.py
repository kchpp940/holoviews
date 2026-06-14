"""Unified option schema and validation mechanism for HoloViews.

This module provides a declarative way to specify configuration options
across renderer, plotting backend, plot classes, and operations, with
consistent validation, helpful error messages, deprecation aliases, and
clear provenance tracking.

Core classes
------------
OptionSpec
    Declarative specification of a single option.
OptionSchema
    A collection of OptionSpecs with unified validation logic.
ValidationError
    Raised when option validation fails. Includes fuzzy-match suggestions
    and source tracing.
OptionCategory
    Enumeration of the four validation entry points.

Usage
-----
1. Define a schema:

    schema = OptionSchema(
        "renderer",
        OptionSpec("dpi", type=int, default=72, bounds=(1, inf),
                   source="holoviews.plotting.renderer.Renderer",
                   description="Render resolution in dots per inch."),
        OptionSpec("fig", type=str, default="auto",
                   allowed=["auto", "png", "svg", None],
                   source="holoviews.plotting.bokeh.renderer.BokehRenderer",
                   deprecated_aliases={"fig_format": "fig"},
                   description="Output format for static figures."),
    )

2. Validate user-supplied kwargs before they are passed downstream:

    cleaned = schema.validate(user_kwargs, context="hv.output()")

"""

from __future__ import annotations

import difflib
import typing as t
from dataclasses import dataclass, field

if t.TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_F = t.TypeVar("_F")
_T = t.TypeVar("_T")

OptionCategoryT = t.Literal[
    "renderer", "plot", "style", "norm", "operation", "extension"
]


class OptionCategory:
    """Enumeration of the six top-level option categories.

    The categories map directly to the four option groups used in
    HoloViews' options system (``style``, ``plot``, ``norm``,
    ``output``) plus the two standalone subsystems (``renderer`` and
    ``operation``).
    """

    RENDERER: OptionCategoryT = "renderer"
    PLOT: OptionCategoryT = "plot"
    STYLE: OptionCategoryT = "style"
    NORM: OptionCategoryT = "norm"
    OPERATION: OptionCategoryT = "operation"
    EXTENSION: OptionCategoryT = "extension"

    ALL: tuple[OptionCategoryT, ...] = (
        "renderer",
        "plot",
        "style",
        "norm",
        "operation",
        "extension",
    )


@dataclass(frozen=True)
class OptionSpec:
    """Declarative specification of a single configuration option.

    Attributes
    ----------
    name : str
        Canonical parameter name.
    type : type or tuple of type
        Allowed Python type(s).  Use ``object`` to accept any type.
    default : Any
        Default value when the option is not supplied.
    allowed : Sequence or set, optional
        Finite set of allowed values.  Takes precedence over ``bounds``
        for membership checks.
    bounds : (low, high) tuple, optional
        Inclusive numeric bounds ``(min, max)``.  Either end may be
        ``None`` to leave that side unbounded.
    source : str, optional
        Fully-qualified class or function that "owns" the option, used in
        error messages to help users locate the documentation.
    description : str, optional
        Short human-readable description shown in help/error output.
    deprecated_aliases : dict[str, str], optional
        Mapping ``{old_name: new_name}``.  When a user passes the old
        name a deprecation warning is emitted and the value is rewritten
        to the canonical name.
    error_hint : str, optional
        Extra text appended to the end of the validation message when
        this specific option fails.
    allow_None : bool, optional
        If ``True`` (the default for specs whose ``default`` is ``None``),
        ``None`` is accepted as a value regardless of ``type``.
    """

    name: str
    type: t.Any = object
    default: t.Any = None
    allowed: Iterable[t.Any] | None = None
    bounds: tuple[t.Any, t.Any] | None = None
    source: str | None = None
    description: str | None = None
    deprecated_aliases: dict[str, str] = field(default_factory=dict)
    error_hint: str | None = None
    allow_None: bool | None = None

    def __post_init__(self) -> None:
        if self.allowed is not None and not isinstance(self.allowed, (list, tuple, set, frozenset)):
            raise TypeError(f"OptionSpec {self.name!r}: 'allowed' must be a finite collection")
        if self.bounds is not None:
            if not (isinstance(self.bounds, tuple) and len(self.bounds) == 2):
                raise TypeError(f"OptionSpec {self.name!r}: 'bounds' must be a (low, high) tuple")
        object.__setattr__(
            self,
            "allow_None",
            self.default is None if self.allow_None is None else self.allow_None,
        )

    # ------------------------------------------------------------------
    # Type-check helpers
    # ------------------------------------------------------------------
    def _is_allowed_type(self, value: t.Any) -> bool:
        if value is None:
            return bool(self.allow_None)
        allowed_type = self.type
        if allowed_type is object:
            return True
        try:
            return isinstance(value, allowed_type)
        except TypeError:
            # `isinstance` with e.g. a Union requires Python 3.10+.
            # Fall back to treating any Union-like type as "pass".
            return True

    def check_value(self, value: t.Any) -> str | None:
        """Validate *value* against the spec.  Returns ``None`` on
        success, or a human-readable error message string on failure."""

        if not self._is_allowed_type(value):
            type_name = (
                self.type.__name__
                if isinstance(self.type, type)
                else str(self.type)
            )
            return (
                f"expected type {type_name}, got {type(value).__name__!r} "
                f"with value {value!r}"
            )
        if value is not None and self.allowed is not None:
            allowed_set = set(self.allowed)
            if value not in allowed_set:
                return (
                    f"value {value!r} not in allowed set "
                    f"{sorted(str(x) for x in allowed_set)}"
                )
        if value is not None and self.bounds is not None:
            lo, hi = self.bounds
            try:
                if lo is not None and value < lo:
                    return f"value {value!r} is below lower bound {lo!r}"
                if hi is not None and value > hi:
                    return f"value {value!r} exceeds upper bound {hi!r}"
            except TypeError:
                return (
                    f"bounds {self.bounds!r} are not comparable with "
                    f"value {value!r} of type {type(value).__name__!r}"
                )
        return None

    # ------------------------------------------------------------------
    # Field-wise overlay
    # ------------------------------------------------------------------
    def overlay(self, other: "OptionSpec") -> "OptionSpec":
        """Produce a new :class:`OptionSpec` by overlaying *other* over
        ``self``.

        For each field the rule is:
          * structural fields (``name``, ``type``, ``default``) are taken
            from *other* unconditionally (other is the "ground truth").
          * constraint fields (``allowed``, ``bounds``) are taken from
            *other* when present, otherwise fall back to ``self``.  This
            means a hand-curated base spec can keep its safety constraints
            even when overlaid with a param-derived spec that lacks them.
          * metadata fields (``source``, ``description``,
            ``error_hint``, ``allow_None``) are taken from *other* when
            non-``None`` else ``self``.
          * ``deprecated_aliases`` is the union of both mappings (values
            from *other* win on name collisions).
        """
        if other.name != self.name:
            raise ValueError(
                f"Cannot overlay OptionSpec {other.name!r} onto {self.name!r}"
            )
        merged_aliases: dict[str, str] = dict(self.deprecated_aliases)
        merged_aliases.update(other.deprecated_aliases)
        return OptionSpec(
            name=other.name,
            type=other.type,
            default=other.default,
            allowed=other.allowed if other.allowed is not None else self.allowed,
            bounds=other.bounds if other.bounds is not None else self.bounds,
            source=other.source or self.source,
            description=other.description or self.description,
            deprecated_aliases=merged_aliases,
            error_hint=other.error_hint or self.error_hint,
            allow_None=other.allow_None
            if other.allow_None is not None
            else self.allow_None,
        )


class ValidationError(ValueError):
    """Raised when one or more options fail schema validation.

    The exception carries:
      * the category (renderer / plot / operation / extension),
      * the list of individual problems (as ``(name, message)`` tuples),
      * the set of allowed option names (for fuzzy matching),
      * the user-supplied ``context`` string describing the call site.

    Calling ``str(exc)`` produces a formatted, user-friendly message
    with suggestions for likely misspellings.
    """

    def __init__(
        self,
        *,
        category: OptionCategoryT,
        problems: Sequence[tuple[str, str]],
        allowed: Sequence[str],
        context: str | None = None,
        source: str | None = None,
    ) -> None:
        self.category = category
        self.problems = list(problems)
        self.allowed = list(allowed)
        self.context = context
        self.source = source
        super().__init__(self._format_message())

    # ------------------------------------------------------------------
    # Message formatting
    # ------------------------------------------------------------------
    def _format_message(self) -> str:
        lines: list[str] = []
        where = f" in {self.context}" if self.context else ""
        owner = f" ({self.source})" if self.source else ""
        category_label = _CATEGORY_LABELS.get(self.category, f"{self.category} option")
        lines.append(
            f"Invalid {category_label}(s){where}{owner}:"
        )
        for name, msg in self.problems:
            suggestion = self._fuzzy(name)
            hint = f"  Did you mean {suggestion!r}?" if suggestion else ""
            lines.append(f"  - {name!r}: {msg}{hint}")
        lines.append("")
        lines.append(
            f"Valid {category_label}s: "
            f"{', '.join(sorted(self.allowed)) or '(none)'}"
        )
        return "\n".join(lines)

    def _fuzzy(self, name: str) -> str | None:
        matches = difflib.get_close_matches(name, self.allowed, n=1, cutoff=0.6)
        return matches[0] if matches else None


class OptionSchema:
    """A named collection of :class:`OptionSpec` instances with unified
    validation logic.

    Parameters
    ----------
    category : OptionCategoryT
        One of ``"renderer"``, ``"plot"``, ``"operation"``, ``"extension"``.
    *specs : OptionSpec
        Option declarations.
    name : str, optional
        Human-readable schema label used in error output.
    source : str, optional
        Default ``source`` value applied to any spec whose own ``source``
        is ``None``.
    """

    def __init__(
        self,
        category: OptionCategoryT,
        *specs: OptionSpec,
        name: str | None = None,
        source: str | None = None,
    ) -> None:
        if category not in OptionCategory.ALL:
            raise ValueError(
                f"Unknown option category {category!r}; "
                f"must be one of {OptionCategory.ALL!r}"
            )
        self.category: OptionCategoryT = category
        self.name = name or f"{category}_schema"
        self.source = source
        self._specs: dict[str, OptionSpec] = {}
        for spec in specs:
            self._add_spec(spec)

    # ------------------------------------------------------------------
    # Building / extending schemas
    # ------------------------------------------------------------------
    def _add_spec(self, spec: OptionSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(
                f"Duplicate option name {spec.name!r} in schema {self.name!r}"
            )
        # Inherit default source when the spec itself doesn't declare one.
        if spec.source is None and self.source is not None:
            object.__setattr__(spec, "source", self.source)
        self._specs[spec.name] = spec

    def extend(self, *specs: OptionSpec) -> "OptionSchema":
        """Return a new schema containing both the existing specs and
        the additional *specs*.  Existing specs may not be overridden."""
        new = OptionSchema(self.category, name=self.name, source=self.source)
        for s in self._specs.values():
            new._add_spec(s)
        for s in specs:
            new._add_spec(s)
        return new

    def merge(self, other: "OptionSchema") -> "OptionSchema":
        """Merge *other* into a new schema.  *other* wins on conflicts
        for the same name, and its :attr:`source` is adopted when the
        existing spec has none."""
        if other.category != self.category:
            raise TypeError(
                "Cannot merge schemas of different categories: "
                f"{self.category!r} vs {other.category!r}"
            )
        new = OptionSchema(self.category, name=self.name, source=self.source)
        for s in self._specs.values():
            new._add_spec(s)
        for s in other._specs.values():
            if s.name in new._specs:
                new._specs.pop(s.name)
            new._add_spec(s)
        return new

    def overlay(self, other: "OptionSchema") -> "OptionSchema":
        """Overlay *other* onto ``self`` using :meth:`OptionSpec.overlay`
        for each conflicting name.

        Unlike :meth:`merge`, which replaces conflicting specs
        wholesale, ``overlay`` preserves constraint fields
        (``allowed``, ``bounds``) from ``self`` when *other* does not
        specify them.  This is the right choice when *other* is derived
        from a param class that only declares types/defaults, while
        ``self`` carries hand-curated safety constraints.
        """
        if other.category != self.category:
            raise TypeError(
                "Cannot overlay schemas of different categories: "
                f"{self.category!r} vs {other.category!r}"
            )
        new = OptionSchema(self.category, name=self.name, source=self.source)
        for s in self._specs.values():
            new._add_spec(s)
        for s in other._specs.values():
            if s.name in new._specs:
                base = new._specs.pop(s.name)
                merged = base.overlay(s)
                new._add_spec(merged)
            else:
                new._add_spec(s)
        return new

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------
    @property
    def specs(self) -> dict[str, OptionSpec]:
        return dict(self._specs)

    @property
    def allowed_names(self) -> list[str]:
        return sorted(self._specs)

    @property
    def defaults(self) -> dict[str, t.Any]:
        return {name: spec.default for name, spec in self._specs.items()}

    def spec_for(self, name: str) -> OptionSpec | None:
        return self._specs.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._specs

    def __len__(self) -> int:
        return len(self._specs)

    def __iter__(self) -> t.Iterator[OptionSpec]:
        return iter(self._specs.values())

    def __repr__(self) -> str:
        return (
            f"OptionSchema(category={self.category!r}, "
            f"name={self.name!r}, specs=<{len(self._specs)} items>)"
        )

    # ------------------------------------------------------------------
    # Core validation entry point
    # ------------------------------------------------------------------
    def validate(
        self,
        options: dict[str, t.Any],
        *,
        context: str | None = None,
        warn: t.Callable[[str], None] | None = None,
        coerce: bool = True,
    ) -> dict[str, t.Any]:
        """Validate *options* against the schema and return a cleaned
        dictionary.

        Parameters
        ----------
        options : dict
            Raw keyword dictionary as supplied by the user.
        context : str, optional
            Short description of the call site, e.g. ``"hv.output()"``.
            Appears in error messages.
        warn : callable, optional
            Function used to emit deprecation warnings.  Defaults to
            :func:`warnings.warn` with a ``DeprecationWarning``.
        coerce : bool, default True
            When ``True``, deprecated aliases are rewritten to their
            canonical names and missing values are filled in from the
            schema defaults.  When ``False`` the returned dict contains
            only keys that were actually present in *options*.

        Returns
        -------
        dict
            Validated (and optionally coerced) keyword dictionary.

        Raises
        ------
        ValidationError
            When one or more options fail the checks.
        """
        if warn is None:
            import warnings

            def _warn(msg: str) -> None:
                warnings.warn(msg, category=DeprecationWarning, stacklevel=3)

            warn = _warn

        rewritten: dict[str, t.Any] = {}
        problems: list[tuple[str, str]] = []
        alias_source: str | None = None

        for raw_name, raw_value in options.items():
            # --- Handle deprecated aliases -----------------------------
            name = raw_name
            for canonical, spec in self._specs.items():
                if raw_name in spec.deprecated_aliases:
                    target = spec.deprecated_aliases[raw_name]
                    warn(
                        f"Option {raw_name!r} is deprecated; use "
                        f"{target!r} instead."
                    )
                    name = target
                    alias_source = spec.source
                    break

            # --- Unknown option ----------------------------------------
            spec = self._specs.get(name)
            if spec is None:
                msg = f"unknown option name"
                problems.append((raw_name, msg))
                continue

            # --- Type / value checks -----------------------------------
            failure = spec.check_value(raw_value)
            if failure is not None:
                tail = f". {spec.error_hint}" if spec.error_hint else ""
                problems.append((raw_name, f"{failure}{tail}"))
                continue
            rewritten[name] = raw_value

        if problems:
            raise ValidationError(
                category=self.category,
                problems=problems,
                allowed=self.allowed_names,
                context=context,
                source=alias_source or self.source,
            )

        if coerce:
            for name, spec in self._specs.items():
                if name not in rewritten:
                    rewritten[name] = spec.default
        return rewritten

    def validate_partial(
        self,
        options: dict[str, t.Any],
        *,
        context: str | None = None,
        warn: t.Callable[[str], None] | None = None,
    ) -> dict[str, t.Any]:
        """Like :meth:`validate`, but silently ignore unknown keys
        instead of raising.  Useful when a dict may contain a mix of
        options for different subsystems."""
        filtered = {
            k: v
            for k, v in options.items()
            if self._is_known(k)
        }
        return self.validate(filtered, context=context, warn=warn, coerce=False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _is_known(self, name: str) -> bool:
        if name in self._specs:
            return True
        return any(
            name in spec.deprecated_aliases for spec in self._specs.values()
        )


# ======================================================================
# Concrete schema registries for the four HoloViews option categories
# ======================================================================
#
# These are intentionally populated lazily: they may be extended by
# third-party backends (e.g. a new plotting backend) at import time.
# Use ``register_*_specs`` or mutate the ``*_SCHEMA`` objects directly.
# ======================================================================

_BASE_RENDERER_SPECS: tuple[OptionSpec, ...] = (
    OptionSpec(
        "backend",
        type=str,
        default=None,
        allow_None=True,
        source="holoviews.plotting.renderer.Renderer",
        description="Lower-case name of the rendering backend.",
    ),
    OptionSpec(
        "center",
        type=bool,
        default=True,
        source="holoviews.plotting.renderer.Renderer",
        description="Whether to center the rendered output.",
    ),
    OptionSpec(
        "dpi",
        type=int,
        default=None,
        bounds=(1, None),
        allow_None=True,
        source="holoviews.plotting.renderer.Renderer",
        description="Render resolution in dots per inch.",
        error_hint="Use a positive integer, e.g. dpi=150.",
    ),
    OptionSpec(
        "fig",
        type=str,
        default="auto",
        allow_None=True,
        allowed=["auto"],
        source="holoviews.plotting.renderer.Renderer",
        deprecated_aliases={"fig_format": "fig"},
        description="Output format for static figures, or None to disable.",
    ),
    OptionSpec(
        "fps",
        type=(int, float),
        default=20,
        bounds=(0, None),
        source="holoviews.plotting.renderer.Renderer",
        description="Frames per second used for animated output formats.",
    ),
    OptionSpec(
        "holomap",
        type=str,
        default="auto",
        allow_None=True,
        allowed=["scrubber", "widgets", None, "auto"],
        source="holoviews.plotting.renderer.Renderer",
        description="Output mode for multi-frame (HoloMap) objects.",
    ),
    OptionSpec(
        "mode",
        type=str,
        default="default",
        allowed=["default", "server"],
        source="holoviews.plotting.renderer.Renderer",
        description="Rendering mode: regular HTML or a live bokeh server Document.",
    ),
    OptionSpec(
        "size",
        type=int,
        default=100,
        bounds=(0, None),
        source="holoviews.plotting.renderer.Renderer",
        description="Rendered size expressed as a percentage.",
    ),
    OptionSpec(
        "widget_location",
        type=str,
        default=None,
        allow_None=True,
        allowed=[
            "left",
            "bottom",
            "right",
            "top",
            "top_left",
            "top_right",
            "bottom_left",
            "bottom_right",
            "left_top",
            "left_bottom",
            "right_top",
            "right_bottom",
        ],
        source="holoviews.plotting.renderer.Renderer",
        description="Position of widgets relative to the plot.",
    ),
    OptionSpec(
        "widget_mode",
        type=str,
        default="embed",
        allowed=["embed", "live"],
        source="holoviews.plotting.renderer.Renderer",
        deprecated_aliases={"widgets": "widget_mode"},
        description="Whether widget frames are embedded or generated live.",
    ),
    OptionSpec(
        "css",
        type=dict,
        default=None,
        allow_None=True,
        source="holoviews.plotting.renderer.Renderer",
        description="Optional CSS attributes applied to the wrapping HTML element.",
    ),
)


def build_renderer_schema(
    backend: str | None = None,
    extra_specs: Iterable[OptionSpec] | None = None,
    renderer_class: type | None = None,
) -> OptionSchema:
    """Build the canonical :class:`OptionSchema` for a Renderer.

    Parameters
    ----------
    backend : str, optional
        When supplied, the returned schema is scoped to that specific
        backend (e.g. ``"bokeh"``) so that backend-specific parameters
        (``theme``, ``webgl``, ``interactive`` ...) can be added by the
        corresponding renderer module.
    extra_specs : iterable of OptionSpec, optional
        Additional backend-specific specs to mix in.
    renderer_class : type, optional
        Concrete Renderer subclass.  When supplied, its ``param``
        descriptors are introspected via :func:`_specs_from_param_class`
        and merged on top of the base set so that backend-specific
        overrides (e.g. the allowed values for ``fig`` and ``holomap``)
        are picked up automatically.  Subclasses are encouraged to pass
        themselves here.

    Returns
    -------
    OptionSchema
    """
    schema = OptionSchema(
        OptionCategory.RENDERER,
        *_BASE_RENDERER_SPECS,
        name=f"{backend or 'base'}_renderer_schema",
        source="holoviews.plotting.renderer.Renderer",
    )
    if renderer_class is not None:
        param_specs = _specs_from_param_class(renderer_class)
        # NOTE: use overlay() rather than merge() here.  Param-derived
        # specs supply authoritative type / default info but typically
        # lack bounds/allowed constraints, which we keep from the
        # hand-curated base specs.
        schema = schema.overlay(
            OptionSchema(OptionCategory.RENDERER, *param_specs)
        )
    if extra_specs:
        schema = schema.extend(*extra_specs)
    return schema


# Base extension / hv.output schema.  Mirrors OutputSettings.allowed /
# defaults in holoviews/util/settings.py but in a declarative form.
_EXTENSION_BASE_SPECS: tuple[OptionSpec, ...] = (
    OptionSpec(
        "backend",
        type=str,
        default=None,
        allow_None=True,
        source="holoviews.util.settings.OutputSettings",
        description="Active plotting backend, e.g. 'bokeh', 'matplotlib', 'plotly'.",
        error_hint="Make sure the backend module is installed and imported via hv.extension(...).",
    ),
    OptionSpec(
        "center",
        type=bool,
        default=True,
        source="holoviews.util.settings.OutputSettings",
        description="Whether to center displayed figures.",
    ),
    OptionSpec(
        "fig",
        type=str,
        default=None,
        allow_None=True,
        source="holoviews.util.settings.OutputSettings",
        description="Static figure output format.",
    ),
    OptionSpec(
        "holomap",
        type=str,
        default=None,
        allow_None=True,
        source="holoviews.util.settings.OutputSettings",
        description="Multi-frame output format.",
    ),
    OptionSpec(
        "widgets",
        type=str,
        default=None,
        allow_None=True,
        allowed=["embed", "live", None],
        source="holoviews.util.settings.OutputSettings",
        deprecated_aliases={"widget_mode": "widgets"},
        description="Widget mode (deprecated alias for widget_mode).",
    ),
    OptionSpec(
        "fps",
        type=(int, float),
        default=None,
        allow_None=True,
        bounds=(0, None),
        source="holoviews.util.settings.OutputSettings",
        description="Animation frame rate.",
    ),
    OptionSpec(
        "max_frames",
        type=int,
        default=500,
        bounds=(0, None),
        source="holoviews.util.settings.OutputSettings",
        description="Maximum number of frames rendered for a HoloMap.",
    ),
    OptionSpec(
        "max_branches",
        type=object,
        default=None,
        allow_None=True,
        source="holoviews.util.settings.OutputSettings",
        deprecated_aliases={},
        description="Deprecated. Kept for backwards compatibility; ignored.",
        error_hint="This option has no effect and will be removed.",
    ),
    OptionSpec(
        "size",
        type=(int, float),
        default=None,
        allow_None=True,
        bounds=(0, None),
        source="holoviews.util.settings.OutputSettings",
        description="Output size expressed as a percentage.",
    ),
    OptionSpec(
        "dpi",
        type=int,
        default=None,
        allow_None=True,
        bounds=(1, None),
        source="holoviews.util.settings.OutputSettings",
        description="Render resolution in dpi.",
    ),
    OptionSpec(
        "filename",
        type=str,
        default=None,
        allow_None=True,
        source="holoviews.util.settings.OutputSettings",
        description="Filename used when saving output.",
    ),
    OptionSpec(
        "info",
        type=bool,
        default=False,
        source="holoviews.util.settings.OutputSettings",
        description="Whether to print auxiliary info alongside the plot.",
    ),
    OptionSpec(
        "widget_location",
        type=str,
        default=None,
        allow_None=True,
        source="holoviews.util.settings.OutputSettings",
        description="Position of widgets relative to the plot area.",
    ),
    OptionSpec(
        "css",
        type=dict,
        default=None,
        allow_None=True,
        source="holoviews.util.settings.OutputSettings",
        description="CSS styling applied to the figure container.",
    ),
    OptionSpec(
        "config",
        type=dict,
        default={},
        source="holoviews.util.extension",
        description="Panel-level config kwargs forwarded to pn.config.",
    ),
    OptionSpec(
        "enable_mathjax",
        type=bool,
        default=False,
        source="holoviews.util.extension",
        description="Whether to enable MathJax rendering for LaTeX labels (bokeh).",
    ),
)


def build_extension_schema(
    extra_specs: Iterable[OptionSpec] | None = None,
    fig_formats: Iterable[t.Any] | None = None,
    holomap_formats: Iterable[t.Any] | None = None,
    backend_list: Iterable[str] | None = None,
) -> OptionSchema:
    """Build the schema validated by ``hv.extension`` / ``hv.output``.

    Parameters
    ----------
    extra_specs : iterable of OptionSpec, optional
        Additional specs to mix in on top of the base extension set.
    fig_formats : iterable, optional
        Override the allowed values for the ``fig`` option.  When not
        supplied the value from the base spec is used (``None`` = accept
        any string or ``None``).  Typical callers such as
        :class:`OutputSettings` pass the dynamically-computed list of
        formats supported by the active backend.
    holomap_formats : iterable, optional
        Same as *fig_formats* but for the ``holomap`` option.
    backend_list : iterable of str, optional
        Override the allowed values for the ``backend`` option.  Used
        by :class:`OutputSettings` to restrict to the currently
        registered backends.
    """
    schema = OptionSchema(
        OptionCategory.EXTENSION,
        *_EXTENSION_BASE_SPECS,
        name="extension_schema",
        source="holoviews.util.settings.OutputSettings",
    )
    # --- Apply dynamic per-backend overrides for the value sets ------
    dynamic: list[OptionSpec] = []
    if fig_formats is not None:
        base = schema.spec_for("fig")
        assert base is not None
        dynamic.append(
            OptionSpec(
                name="fig",
                type=base.type,
                default=base.default,
                allow_None=base.allow_None,
                allowed=list(fig_formats),
                source=base.source,
                description=base.description,
                deprecated_aliases=base.deprecated_aliases,
                error_hint=base.error_hint,
            )
        )
    if holomap_formats is not None:
        base = schema.spec_for("holomap")
        assert base is not None
        dynamic.append(
            OptionSpec(
                name="holomap",
                type=base.type,
                default=base.default,
                allow_None=base.allow_None,
                allowed=list(holomap_formats),
                source=base.source,
                description=base.description,
                deprecated_aliases=base.deprecated_aliases,
                error_hint=base.error_hint,
            )
        )
    if backend_list is not None:
        base = schema.spec_for("backend")
        assert base is not None
        dynamic.append(
            OptionSpec(
                name="backend",
                type=base.type,
                default=base.default,
                allow_None=base.allow_None,
                allowed=list(backend_list),
                source=base.source,
                description=base.description,
                deprecated_aliases=base.deprecated_aliases,
                error_hint=(
                    base.error_hint
                    or "Make sure the backend module is installed and "
                    "imported via hv.extension(...)."
                ),
            )
        )
    if dynamic:
        schema = schema.merge(
            OptionSchema(OptionCategory.EXTENSION, *dynamic)
        )
    if extra_specs:
        schema = schema.extend(*extra_specs)
    return schema


# ----------------------------------------------------------------------
# Plot option base schema.  Concrete per-element plots typically add
# many more params; this schema covers the common ones shared across
# GenericElementPlot and friends.
# ----------------------------------------------------------------------
_PLOT_BASE_SPECS: tuple[OptionSpec, ...] = (
    OptionSpec(
        "fontsize",
        type=object,
        default=None,
        allow_None=True,
        source="holoviews.plotting.plot.DimensionedPlot",
        description="Font size(s) applied to axes, labels, title, etc.",
    ),
    OptionSpec(
        "fontscale",
        type=(int, float),
        default=1.0,
        bounds=(0, None),
        source="holoviews.plotting.plot.DimensionedPlot",
        description="Scaling factor applied to all text elements.",
    ),
    OptionSpec(
        "show_title",
        type=bool,
        default=True,
        source="holoviews.plotting.plot.DimensionedPlot",
        description="Whether the plot title is visible.",
    ),
    OptionSpec(
        "title",
        type=str,
        default=None,
        allow_None=True,
        source="holoviews.plotting.plot.DimensionedPlot",
        description="Explicit title string overriding the default.",
    ),
    OptionSpec(
        "normalize",
        type=bool,
        default=True,
        source="holoviews.plotting.plot.DimensionedPlot",
        description="Whether to normalize ranges across frames.",
    ),
    OptionSpec(
        "projection",
        type=object,
        default=None,
        allow_None=True,
        source="holoviews.plotting.plot.DimensionedPlot",
        description="Cartopy/geo projection used for the axes.",
    ),
    OptionSpec(
        "apply_ranges",
        type=bool,
        default=True,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Whether to apply data ranges to the axes.",
    ),
    OptionSpec(
        "apply_extents",
        type=bool,
        default=True,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Whether to apply explicit extents to the axes.",
    ),
    OptionSpec(
        "bgcolor",
        type=object,
        default=None,
        allow_None=True,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Background color of the plot area.",
    ),
    OptionSpec(
        "hooks",
        type=list,
        default=[],
        source="holoviews.plotting.plot.GenericElementPlot",
        description="List of callables invoked with (plot, element) after drawing.",
    ),
    OptionSpec(
        "invert_axes",
        type=bool,
        default=False,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Swap the x and y axes.",
    ),
    OptionSpec(
        "invert_xaxis",
        type=bool,
        default=False,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Reverse the x-axis direction.",
    ),
    OptionSpec(
        "invert_yaxis",
        type=bool,
        default=False,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Reverse the y-axis direction.",
    ),
    OptionSpec(
        "logx",
        type=bool,
        default=False,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Use a logarithmic scale on the x-axis.",
    ),
    OptionSpec(
        "logy",
        type=bool,
        default=False,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Use a logarithmic scale on the y-axis.",
    ),
    OptionSpec(
        "padding",
        type=object,
        default=0,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Padding added around the data range as a fraction.",
    ),
    OptionSpec(
        "show_legend",
        type=bool,
        default=True,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Whether to draw the legend.",
    ),
    OptionSpec(
        "show_grid",
        type=bool,
        default=False,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Whether to draw a grid.",
    ),
    OptionSpec(
        "xaxis",
        type=str,
        default=None,
        allow_None=True,
        allowed=["bottom", "top", "bare", None],
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Position and style of the x axis.",
    ),
    OptionSpec(
        "yaxis",
        type=str,
        default=None,
        allow_None=True,
        allowed=["left", "right", "bare", None],
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Position and style of the y axis.",
    ),
    OptionSpec(
        "xlabel",
        type=str,
        default=None,
        allow_None=True,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Override label for the x axis.",
    ),
    OptionSpec(
        "ylabel",
        type=str,
        default=None,
        allow_None=True,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Override label for the y axis.",
    ),
    OptionSpec(
        "xlim",
        type=tuple,
        default=None,
        allow_None=True,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Explicit (low, high) limits for the x axis.",
    ),
    OptionSpec(
        "ylim",
        type=tuple,
        default=None,
        allow_None=True,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Explicit (low, high) limits for the y axis.",
    ),
    OptionSpec(
        "zlim",
        type=tuple,
        default=None,
        allow_None=True,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Explicit (low, high) limits for the z/color axis.",
    ),
    OptionSpec(
        "xrotation",
        type=int,
        default=0,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Rotation angle in degrees for x-axis tick labels.",
    ),
    OptionSpec(
        "yrotation",
        type=int,
        default=0,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Rotation angle in degrees for y-axis tick labels.",
    ),
    OptionSpec(
        "xticks",
        type=object,
        default=None,
        allow_None=True,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Explicit tick values for the x axis.",
    ),
    OptionSpec(
        "yticks",
        type=object,
        default=None,
        allow_None=True,
        source="holoviews.plotting.plot.GenericElementPlot",
        description="Explicit tick values for the y axis.",
    ),
)


def build_plot_schema(
    plot_class: type | None = None,
    extra_specs: Iterable[OptionSpec] | None = None,
) -> OptionSchema:
    """Build an :class:`OptionSchema` for a Plot subclass.

    When a ``param.Parameterized`` *plot_class* is supplied its
    ``param`` descriptors are converted into :class:`OptionSpec`
    entries and merged on top of the base set so that backend-specific
    parameters are covered automatically.
    """
    schema = OptionSchema(
        OptionCategory.PLOT,
        *_PLOT_BASE_SPECS,
        name=(plot_class.__name__ if plot_class else "base") + "_plot_schema",
        source=(
            f"{plot_class.__module__}.{plot_class.__name__}"
            if plot_class is not None
            else "holoviews.plotting.plot.Plot"
        ),
    )
    if plot_class is not None:
        param_specs = _specs_from_param_class(plot_class)
        # NOTE: use overlay() rather than merge() here.  Param-derived
        # specs supply authoritative type / default info but typically
        # lack bounds/allowed constraints, which we keep from the
        # hand-curated base specs.
        schema = schema.overlay(
            OptionSchema(OptionCategory.PLOT, *param_specs)
        )
    if extra_specs:
        schema = schema.extend(*extra_specs)
    return schema


# ----------------------------------------------------------------------
# Operation base schema.
# ----------------------------------------------------------------------
_OPERATION_BASE_SPECS: tuple[OptionSpec, ...] = (
    OptionSpec(
        "group",
        type=str,
        default="Operation",
        source="holoviews.core.operation.Operation",
        description="Group label used for the operation output.",
    ),
    OptionSpec(
        "dynamic",
        type=object,
        default="default",
        allowed=["default", True, False],
        source="holoviews.core.operation.Operation",
        description="Whether the operation returns a DynamicMap.",
    ),
    OptionSpec(
        "input_ranges",
        type=(dict, tuple),
        default={},
        allow_None=True,
        source="holoviews.core.operation.Operation",
        description="Optional normalization ranges applied to the input.",
    ),
    OptionSpec(
        "link_inputs",
        type=bool,
        default=False,
        source="holoviews.core.operation.Operation",
        description="Whether to link Range streams from the input to the output.",
    ),
    OptionSpec(
        "streams",
        type=(dict, list),
        default=[],
        source="holoviews.core.operation.Operation",
        description="Streams attached to a dynamically-applied operation.",
    ),
)


def build_operation_schema(
    operation_class: type | None = None,
    extra_specs: Iterable[OptionSpec] | None = None,
) -> OptionSchema:
    """Build an :class:`OptionSchema` for an Operation subclass."""
    schema = OptionSchema(
        OptionCategory.OPERATION,
        *_OPERATION_BASE_SPECS,
        name=(
            operation_class.__name__ if operation_class else "base"
        ) + "_operation_schema",
        source=(
            f"{operation_class.__module__}.{operation_class.__name__}"
            if operation_class is not None
            else "holoviews.core.operation.Operation"
        ),
    )
    if operation_class is not None:
        param_specs = _specs_from_param_class(operation_class)
        schema = schema.merge(
            OptionSchema(OptionCategory.OPERATION, *param_specs)
        )
    if extra_specs:
        schema = schema.extend(*extra_specs)
    return schema


# ----------------------------------------------------------------------
# Internal helpers -----------------------------------------------------
# ----------------------------------------------------------------------
def _specs_from_param_class(parameterized_cls: type) -> list[OptionSpec]:
    """Convert a ``param.Parameterized`` subclass into a list of
    :class:`OptionSpec` objects by introspecting its parameters.

    Only a small subset of ``param`` types is mapped exactly; unknown
    parameter types fall back to ``type=object`` which accepts any
    Python value but still lets us catch misspelled names.
    """
    import param

    specs: list[OptionSpec] = []
    for name, p in parameterized_cls.param.objects(instance=False).items():
        if name in ("name",):
            # Skip the universal "name" param that every Parameterized
            # class receives — it's never a user-facing option.
            continue
        ptype = _param_to_python_type(p)
        default = p.default
        allowed: Iterable | None = None
        bounds: tuple | None = None
        if isinstance(p, param.Selector):
            try:
                allowed = list(p.objects) if p.objects else None
            except Exception:
                allowed = None
        if isinstance(p, param.Number) and not isinstance(p, param.Boolean):
            lo = getattr(p, "bounds", None)
            if lo is not None:
                bounds = tuple(lo)  # type: ignore[arg-type]
        allow_None = getattr(p, "allow_None", False) or default is None
        source = f"{parameterized_cls.__module__}.{parameterized_cls.__name__}"
        specs.append(
            OptionSpec(
                name=name,
                type=ptype,
                default=default,
                allowed=allowed,
                bounds=bounds,
                source=source,
                description=getattr(p, "doc", None),
                allow_None=allow_None,
            )
        )
    return specs


def _param_to_python_type(p: t.Any) -> t.Any:
    """Best-effort mapping from a ``param.Parameter`` to the Python
    type(s) we accept at validation time."""
    import param

    if isinstance(p, param.Integer):
        return int
    if isinstance(p, param.Number):
        return (int, float)
    if isinstance(p, param.Boolean):
        return bool
    if isinstance(p, param.String):
        return str
    if isinstance(p, param.List):
        return list
    if isinstance(p, param.Dict):
        return dict
    if isinstance(p, param.Tuple):
        return tuple
    if isinstance(p, param.Callable):
        return callable
    if isinstance(p, param.ClassSelector):
        cs = t.cast("param.ClassSelector", p)
        if isinstance(cs.class_, (tuple, list)):
            return tuple(cs.class_)  # type: ignore[arg-type]
        return cs.class_
    # Fall back to "any type".
    return object


__all__ = [
    "OptionCategory",
    "OptionSpec",
    "OptionSchema",
    "ValidationError",
    "build_extension_schema",
    "build_norm_schema",
    "build_operation_schema",
    "build_plot_schema",
    "build_renderer_schema",
    "build_style_schema",
]


# ======================================================================
# Friendly labels used in error messages for each category
# ======================================================================

_CATEGORY_LABELS: dict[OptionCategoryT, str] = {
    "renderer": "renderer option",
    "plot": "plot option",
    "style": "style option",
    "norm": "normalization option",
    "operation": "operation option",
    "extension": "display extension option",
}


# ======================================================================
# Norm / style option schemas
# ======================================================================

_NORM_BASE_SPECS: tuple[OptionSpec, ...] = (
    OptionSpec(
        "framewise",
        type=bool,
        default=False,
        source="holoviews.plotting.plot.DimensionedPlot",
        description="Whether normalization is applied per-frame.",
    ),
    OptionSpec(
        "axiswise",
        type=bool,
        default=False,
        source="holoviews.plotting.plot.DimensionedPlot",
        description="Whether normalization is applied per-axis.",
    ),
)


def build_norm_schema(extra_specs: Iterable[OptionSpec] | None = None) -> OptionSchema:
    """Build the canonical :class:`OptionSchema` for norm options.

    Norm options control how data is normalised across frames and axes
    in animated and multi-element plots.
    """
    schema = OptionSchema(
        OptionCategory.NORM,
        *_NORM_BASE_SPECS,
        name="norm_schema",
        source="holoviews.plotting.plot.DimensionedPlot",
    )
    if extra_specs:
        schema = schema.extend(*extra_specs)
    return schema


def build_style_schema(
    style_opts: Iterable[str],
    *,
    backend: str | None = None,
    element_name: str | None = None,
    extra_specs: Iterable[OptionSpec] | None = None,
) -> OptionSchema:
    """Build an :class:`OptionSchema` for a Plot subclass's style options.

    Style options are the keyword arguments forwarded directly to the
    underlying backend's drawing calls (e.g. ``color``, ``line_width``,
    ``marker``).  They are inherently backend-specific and are declared
    as lists of strings on each Plot class (``Plot.style_opts``).

    Parameters
    ----------
    style_opts : iterable of str
        The list of allowed style option names (from ``Plot.style_opts``
        after alias expansion).
    backend : str, optional
        Name of the plotting backend (e.g. ``"bokeh"``).  Used in error
        messages and for the schema's default ``source``.
    element_name : str, optional
        Name of the element/view class these style options apply to
        (e.g. ``"Curve"``).  Used in error messages.
    extra_specs : iterable of OptionSpec, optional
        Additional specs to mix in (e.g. for backend-specific aliases
        or deprecations).
    """
    source = (
        f"holoviews.plotting.{backend}.{element_name or 'Element'}"
        if backend
        else "holoviews.plotting.plot.Plot"
    )
    name_parts = [element_name or "element", backend, "style_schema"]
    name = "_".join(p for p in name_parts if p)

    specs: list[OptionSpec] = []
    for opt in style_opts:
        specs.append(
            OptionSpec(
                name=opt,
                type=object,
                default=None,
                allow_None=True,
                source=source,
                description=f"Style option forwarded to the {backend or 'backend'} renderer.",
            )
        )

    schema = OptionSchema(OptionCategory.STYLE, *specs, name=name, source=source)
    if extra_specs:
        schema = schema.extend(*extra_specs)
    return schema
