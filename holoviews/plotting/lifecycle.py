"""
Unified Plot Lifecycle Hook Layer for HoloViews.

This module provides a standardized lifecycle framework for plot initialization
across all backends (Bokeh, Plotly, Matplotlib). It defines clear lifecycle
phases and extensible hook points that enable cross-backend features like
theming, debugging, and custom plugins without requiring per-backend patches.

Architecture Overview:

    LifecyclePhase
        Enumeration of all standardized lifecycle phases.

    LifecycleContext
        Context object passed between phases, carrying plot state and data.
        Each phase produces its output object(s) through the context, and
        subsequent phases (and hooks) can read and modify them.

    LifecycleHook
        Base class for custom hooks that can be registered to run at
        specific lifecycle phases (before or after creation).

    LifecycleMixin
        Mixin class that provides lifecycle management capabilities to
        backend-specific Plot classes.

Lifecycle Phases (in order):

    1.  PRE_INIT        - Before any plot initialization begins
    2.  CREATE_FIGURE   - Create the figure/canvas
    3.  CREATE_LAYOUT   - Create layout/container
    4.  CREATE_AXES     - Create axes with labels, ticks, ranges
    5.  CREATE_GLYPHS   - Create glyphs/artists/traces from data
    6.  CREATE_LEGEND   - Create legend
    7.  CREATE_COLORBAR - Create colorbar
    8.  CREATE_TOOLS    - Create tools (hover, zoom, pan, etc.)
    9.  FINALIZE_STYLE  - Apply final styling (themes, fonts, etc.)
    10. POST_INIT       - After all initialization is complete

Each creation phase (create_*) runs in the pattern:
    run hooks BEFORE phase -> run backend creation -> run hooks AFTER phase
This ensures hooks always have access to the created, mutable objects.

Lifecycle Phase Contract
========================

Each phase has a well-defined contract specifying which objects are:
- R/O: Read-only - available for inspection but modifications may be overwritten
- R/W: Read-write - modifications will be preserved through subsequent phases
- OVERWRITTEN: Will be overwritten by a later phase - modify at your own risk

Legend:
    [R/O]  - Object exists, may be overwritten by later phases
    [R/W]  - Object exists, modifications are preserved
    [NEW]  - Object is created by this phase's create_fn
    [N/A]  - Object does not exist yet

Phase: PRE_INIT
---------------
Runs before any backend-specific initialization.
- element:   [R/W]  The Element being plotted
- ranges:    [R/W]  Computed ranges for the plot
- key:       [R/W]  The current key/frame being rendered
- figure:    [N/A]
- axes:      [N/A]
- glyphs:    [N/A]
- legend:    [N/A]
- colorbar:  [N/A]
- tools:     [N/A]
- layout:    [N/A]
- state:     [N/A]
Notes: Good place to validate input or preprocess data.

Phase: CREATE_FIGURE
--------------------
Creates the figure/canvas object.
- Before:
  figure:    [N/A]
  All other objects from PRE_INIT are [R/O]
- After:
  figure:    [NEW, R/W]  The created figure object
  layout:    [NEW, R/W]  The figure as layout container
  element:   [R/O]
  ranges:    [R/O]
  axes:      [OVERWRITTEN]  Initial axes may be replaced by CREATE_AXES
  Others:    [N/A]
Notes: Figure object is fully mutable after this phase.

Phase: CREATE_LAYOUT
--------------------
Creates layout/container (primarily for Plotly and composite plots).
- Before:
  figure:    [R/O]
- After:
  layout:    [NEW, R/W]  Layout dict (Plotly) or layout object
  figure:    [R/O]
  Others:    Inherit from CREATE_FIGURE
Notes: For Bokeh/MPL, layout is often the same as figure.

Phase: CREATE_AXES
------------------
Creates and configures axes with labels, ticks, ranges.
This is the FINAL phase for axes configuration - modifications here are preserved.
- Before:
  figure:    [R/O]
  glyphs:    [R/O]  Glyphs may be created before axes (backends vary)
- After:
  axes:      [NEW, R/W]  Axes tuple (xaxis, yaxis) or Axes object
  figure:    [R/O]
  glyphs:    [R/O]
  All axes properties (labels, ticks, ranges, grid, log scale, etc.) are FINAL
  after this phase - no subsequent phase will overwrite them.
Notes: This is the recommended phase for modifying axes properties.

Phase: CREATE_GLYPHS
--------------------
Creates glyphs/artists/traces from data.
- Before:
  figure:    [R/O]
  axes:      [R/O]  Do not modify axes here - changes may be overwritten!
  element:   [R/O]
  ranges:    [R/O]
- After:
  glyphs:    [NEW, R/W]  The created glyph/artist/trace object(s)
  figure:    [R/O]
  axes:      [R/W]  Axes are FINAL after CREATE_AXES
Notes: Glyph creation order varies by backend:
  - Bokeh: CREATE_GLYPHS before CREATE_AXES
  - MPL:   CREATE_GLYPHS before CREATE_AXES
  - Plotly: CREATE_GLYPHS before CREATE_LAYOUT and CREATE_AXES

Phase: CREATE_LEGEND
--------------------
Creates the legend.
- Before:
  figure:    [R/O]
  axes:      [R/W]  (FINAL - from CREATE_AXES)
  glyphs:    [R/O]
- After:
  legend:    [NEW, R/W]  The legend object (or None if no legend)
  figure:    [R/O]
  axes:      [R/W]  (FINAL)
  glyphs:    [R/O]

Phase: CREATE_COLORBAR
----------------------
Creates the colorbar.
- Before:
  figure:    [R/O]
  axes:      [R/W]  (FINAL)
  glyphs:    [R/O]
  legend:    [R/O]
- After:
  colorbar:  [NEW, R/W]  The colorbar object (or None if no colorbar)
  figure:    [R/O]
  axes:      [R/W]  (FINAL)
  glyphs:    [R/O]
  legend:    [R/O]

Phase: CREATE_TOOLS
-------------------
Creates tools (hover, zoom, pan, etc.).
- Before:
  figure:    [R/O]
  axes:      [R/W]  (FINAL)
  glyphs:    [R/O]
  legend:    [R/O]
  colorbar:  [R/O]
- After:
  tools:     [NEW, R/W]  Dict of tool objects (hover, zoom, etc.)
  figure:    [R/O]
  axes:      [R/W]  (FINAL)
  Others:    [R/O]

Phase: FINALIZE_STYLE
---------------------
Applies final styling and executes hooks.
This is the LAST phase where modifications should be made.
- Before:
  ALL objects are available and [R/W]
  figure:    [R/W]
  axes:      [R/W]  (FINAL)
  glyphs:    [R/W]
  legend:    [R/W]
  colorbar:  [R/W]
  tools:     [R/W]
- After:
  state:     [NEW, R/W]  The final plot state (figure object)
  ALL objects are [R/W] but this is the last chance to modify them.
Notes: This is the recommended phase for theme application and final touches.
       All modifications here are guaranteed to be preserved.

Phase: POST_INIT
----------------
After all initialization is complete.
- Before:
  ALL objects are [R/W]
  state:     [R/W]  The final plot state
- After:
  Same as before
Notes: Good place for cleanup, logging, or post-processing that doesn't
       modify the visual output.

Summary of Key Modification Points:
===================================
- For axes labels/ticks/ranges:   Use CREATE_AXES [after]
- For glyph styling:              Use CREATE_GLYPHS [after] or FINALIZE_STYLE
- For legend customization:       Use CREATE_LEGEND [after] or FINALIZE_STYLE
- For colorbar customization:     Use CREATE_COLORBAR [after] or FINALIZE_STYLE
- For tool configuration:         Use CREATE_TOOLS [after] or FINALIZE_STYLE
- For figure-wide styling:        Use FINALIZE_STYLE [before/after]
- For themes:                     Use FINALIZE_STYLE (guaranteed final)
- For debugging/logging:          Use any phase, or POST_INIT

WARNING:
- Do NOT modify axes in CREATE_GLYPHS [after] - they may be overwritten by
  CREATE_AXES in some backends.
- Do NOT rely on object presence in phases marked [N/A].
- Always check for None before accessing optional objects (legend, colorbar, etc.).

Usage for Backend Integration:

    class MyBackendPlot(LifecycleMixin, BasePlot):
        def initialize_plot(self, ranges=None):
            ctx = LifecycleContext(
                plot=self,
                element=self.hmap.last,
                ranges=ranges,
                key=self.keys[-1]
            )

            # Phase 1: PRE_INIT
            ctx = self.run_lifecycle_phase(LifecyclePhase.PRE_INIT, ctx)

            # Phase 2: CREATE_FIGURE - real figure creation via create_fn
            def _create_figure(ctx):
                fig = create_my_figure()
                return ctx.update(figure=fig)
            ctx = self.run_lifecycle_phase(
                LifecyclePhase.CREATE_FIGURE, ctx, _create_figure
            )

            # Phase 3: CREATE_AXES - real axes creation via create_fn
            def _create_axes(ctx):
                ax = create_my_axes(ctx.figure)
                return ctx.update(axes=ax)
            ctx = self.run_lifecycle_phase(
                LifecyclePhase.CREATE_AXES, ctx, _create_axes
            )

            # ... continue through all phases

            return ctx.state

Usage for Custom Hooks:

    class MyThemeHook(LifecycleHook):
        @hook_for(LifecyclePhase.CREATE_FIGURE, when="after")
        def style_figure(self, ctx):
            ctx.figure.background_fill_color = "#f0f0f0"
            return ctx

    BokehElementPlot.register_lifecycle_hook(MyThemeHook())
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union

from ..core import Element


class LifecyclePhase(str, Enum):
    """Enumeration of all standardized plot lifecycle phases."""

    PRE_INIT = "pre_init"
    CREATE_FIGURE = "create_figure"
    CREATE_LAYOUT = "create_layout"
    CREATE_AXES = "create_axes"
    CREATE_GLYPHS = "create_glyphs"
    CREATE_LEGEND = "create_legend"
    CREATE_COLORBAR = "create_colorbar"
    CREATE_TOOLS = "create_tools"
    FINALIZE_STYLE = "finalize_style"
    POST_INIT = "post_init"

    @classmethod
    def all_phases(cls) -> List["LifecyclePhase"]:
        """Return all phases in the correct execution order."""
        return [
            cls.PRE_INIT,
            cls.CREATE_FIGURE,
            cls.CREATE_LAYOUT,
            cls.CREATE_AXES,
            cls.CREATE_GLYPHS,
            cls.CREATE_LEGEND,
            cls.CREATE_COLORBAR,
            cls.CREATE_TOOLS,
            cls.FINALIZE_STYLE,
            cls.POST_INIT,
        ]

    @property
    def is_creation_phase(self) -> bool:
        """Whether this is a creation phase (has before/after hooks)."""
        return self.value.startswith("create_")

    def __lt__(self, other: "LifecyclePhase") -> bool:
        """Compare phases based on execution order."""
        phases = self.all_phases()
        return phases.index(self) < phases.index(other)

    def __le__(self, other: "LifecyclePhase") -> bool:
        return self < other or self == other

    def __gt__(self, other: "LifecyclePhase") -> bool:
        return not self <= other

    def __ge__(self, other: "LifecyclePhase") -> bool:
        return not self < other


@dataclass
class LifecycleContext:
    """
    Context object passed through all lifecycle phases.

    Carries plot state, data, and backend-specific objects between phases.
    Backends can extend this by adding custom keys to the `extra` dict.

    Each creation phase is responsible for setting its corresponding
    attribute(s) on the context. Hooks running AFTER the phase can read
    and modify these objects.

    Attributes:
        plot: The Plot instance being initialized.
        element: The Element being plotted.
        ranges: Computed ranges for the plot.
        key: The current key/frame being rendered.
        figure: The created figure object (set in CREATE_FIGURE).
        layout: The layout/container object (set in CREATE_LAYOUT).
        axes: The axes object(s) (set in CREATE_AXES).
        glyphs: The created glyphs/artists/traces (set in CREATE_GLYPHS).
        legend: The legend object (set in CREATE_LEGEND).
        colorbar: The colorbar object (set in CREATE_COLORBAR).
        tools: The tools list or tool objects (set in CREATE_TOOLS).
        state: The final plot state (set in POST_INIT).
        extra: Dict for backend-specific extensions.
    """

    plot: Any
    element: Optional[Element] = None
    ranges: Optional[Dict] = None
    key: Any = None

    figure: Any = None
    layout: Any = None
    axes: Any = None
    glyphs: Any = None
    legend: Any = None
    colorbar: Any = None
    tools: Any = None
    state: Any = None

    extra: Dict[str, Any] = field(default_factory=dict)

    def update(self, **kwargs) -> "LifecycleContext":
        """Update context attributes and return self for chaining."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                self.extra[key] = value
        return self

    def get(self, key: str, default: Any = None) -> Any:
        """Get an attribute, checking both standard attrs and extra dict."""
        if hasattr(self, key):
            return getattr(self, key)
        return self.extra.get(key, default)


T = TypeVar("T", bound="LifecycleHook")


def hook_for(phase: LifecyclePhase, when: str = "after") -> Callable:
    """
    Decorator to mark a method as a hook for a specific lifecycle phase.

    Args:
        phase: The lifecycle phase to hook into.
        when: When to run the hook - "before", "after", or "both".
              For non-creation phases (pre_init, finalize_style, post_init),
              "after" means the hook runs during the phase itself.

    Usage:
        class MyHook(LifecycleHook):
            @hook_for(LifecyclePhase.CREATE_FIGURE, when="after")
            def on_create_figure(self, ctx):
                ctx.figure.background_fill_color = "red"
                return ctx
    """

    def decorator(func: Callable) -> Callable:
        func._lifecycle_phase = phase
        func._lifecycle_when = when
        return func

    return decorator


class LifecycleHook:
    """
    Base class for lifecycle hooks.

    Subclasses should define methods decorated with @hook_for to handle
    specific lifecycle phases. Hook methods receive a LifecycleContext
    and must return it (possibly modified).

    For creation phases (create_figure, create_axes, etc.), hooks can run
    BEFORE the actual creation (to configure parameters) or AFTER (to
    modify the created object).

    A hook can also implement `should_run` to conditionally skip execution.
    """

    priority: int = 0

    def __init__(self, priority: int = 0):
        self.priority = priority
        self._phase_handlers: Dict[tuple, Callable] = {}
        self._discover_phase_handlers()

    def _discover_phase_handlers(self) -> None:
        """Discover methods decorated with @hook_for."""
        for _, method in inspect.getmembers(self, predicate=inspect.ismethod):
            phase = getattr(method, "_lifecycle_phase", None)
            when = getattr(method, "_lifecycle_when", "after")
            if phase is not None:
                if when == "both":
                    self._phase_handlers[(phase, "before")] = method
                    self._phase_handlers[(phase, "after")] = method
                else:
                    self._phase_handlers[(phase, when)] = method

    def should_run(self, phase: LifecyclePhase, when: str, ctx: LifecycleContext) -> bool:
        """
        Determine if this hook should run for the given phase, timing, and context.

        Override to add conditional logic.
        """
        return (phase, when) in self._phase_handlers

    def run(self, phase: LifecyclePhase, when: str, ctx: LifecycleContext) -> LifecycleContext:
        """Run the hook for the given phase and timing if applicable."""
        if not self.should_run(phase, when, ctx):
            return ctx
        handler = self._phase_handlers.get((phase, when))
        if handler is None:
            return ctx
        return handler(ctx)

    def __lt__(self, other: "LifecycleHook") -> bool:
        """Sort hooks by priority (higher priority runs first)."""
        return self.priority > other.priority


class LifecycleMixin:
    """
    Mixin class that provides lifecycle management capabilities.

    Backend-specific Plot classes should inherit from this mixin to
    gain lifecycle hook support. The mixin maintains a registry of
    hooks and provides methods to run lifecycle phases.

    The key method is `run_lifecycle_phase(phase, ctx, create_fn)`:
    1. Runs all "before" hooks for the phase
    2. Calls create_fn(ctx) to do the actual backend creation
    3. Runs all "after" hooks for the phase (with created objects in ctx)
    4. Returns the (possibly modified) context

    For non-creation phases (pre_init, finalize_style, post_init),
    create_fn can be None and hooks just run once.

    Class Attributes:
        _class_lifecycle_hooks: List of hooks registered at the class level.

    Instance Attributes:
        _instance_lifecycle_hooks: List of hooks registered on the instance.
        _current_lifecycle_phase: The phase currently being executed.
    """

    _class_lifecycle_hooks: List[LifecycleHook] = []

    def __init__(self, *args, **kwargs):
        self._instance_lifecycle_hooks: List[LifecycleHook] = []
        self._current_lifecycle_phase: Optional[LifecyclePhase] = None
        self._current_lifecycle_when: Optional[str] = None
        super().__init__(*args, **kwargs)

    @classmethod
    def register_lifecycle_hook(cls, hook: LifecycleHook) -> None:
        """Register a lifecycle hook for all instances of this class."""
        if not isinstance(hook, LifecycleHook):
            raise TypeError(f"Expected LifecycleHook, got {type(hook).__name__}")
        if hook not in cls._class_lifecycle_hooks:
            cls._class_lifecycle_hooks.append(hook)
            cls._class_lifecycle_hooks.sort()

    @classmethod
    def unregister_lifecycle_hook(cls, hook: LifecycleHook) -> None:
        """Unregister a class-level lifecycle hook."""
        if hook in cls._class_lifecycle_hooks:
            cls._class_lifecycle_hooks.remove(hook)

    def add_lifecycle_hook(self, hook: LifecycleHook) -> None:
        """Add a lifecycle hook specific to this instance."""
        if not isinstance(hook, LifecycleHook):
            raise TypeError(f"Expected LifecycleHook, got {type(hook).__name__}")
        if hook not in self._instance_lifecycle_hooks:
            self._instance_lifecycle_hooks.append(hook)
            self._instance_lifecycle_hooks.sort()

    def remove_lifecycle_hook(self, hook: LifecycleHook) -> None:
        """Remove an instance-level lifecycle hook."""
        if hook in self._instance_lifecycle_hooks:
            self._instance_lifecycle_hooks.remove(hook)

    def _get_all_hooks(self) -> List[LifecycleHook]:
        """Get all hooks (class-level + instance-level) sorted by priority."""
        all_hooks = list(self._class_lifecycle_hooks) + list(self._instance_lifecycle_hooks)
        all_hooks.sort()
        return all_hooks

    def run_lifecycle_phase(
        self,
        phase: LifecyclePhase,
        ctx: LifecycleContext,
        create_fn: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
    ) -> LifecycleContext:
        """
        Run a single lifecycle phase with before/after hooks.

        Execution order:
        1. Set current phase
        2. Run "before" hooks (if create_fn is provided)
        3. Call create_fn(ctx) to do the actual work
        4. Run "after" hooks (with objects available in ctx)
        5. Return the (possibly modified) context

        If create_fn is None, only "after" hooks run (notification-only).
        All phases support before/after pattern when a create_fn is provided.

        Args:
            phase: The lifecycle phase to run.
            ctx: The lifecycle context.
            create_fn: Optional callable that performs the actual
                backend-specific work. Receives and returns the context.

        Returns:
            The (possibly modified) context.
        """
        self._current_lifecycle_phase = phase

        all_hooks = self._get_all_hooks()

        if create_fn is not None:
            self._current_lifecycle_when = "before"
            for hook in all_hooks:
                if hook.should_run(phase, "before", ctx):
                    ctx = hook.run(phase, "before", ctx)

            ctx = create_fn(ctx)

            self._current_lifecycle_when = "after"
            for hook in all_hooks:
                if hook.should_run(phase, "after", ctx):
                    ctx = hook.run(phase, "after", ctx)
        else:
            self._current_lifecycle_when = "after"
            for hook in all_hooks:
                if hook.should_run(phase, "after", ctx):
                    ctx = hook.run(phase, "after", ctx)

        return ctx

    @property
    def current_lifecycle_phase(self) -> Optional[LifecyclePhase]:
        """Get the currently executing lifecycle phase."""
        return self._current_lifecycle_phase

    @property
    def current_lifecycle_when(self) -> Optional[str]:
        """Get the current timing ("before" or "after") within the phase."""
        return self._current_lifecycle_when

    def run_full_lifecycle(
        self,
        ctx: LifecycleContext,
        create_figure: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
        create_layout: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
        create_axes: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
        create_glyphs: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
        create_legend: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
        create_colorbar: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
        create_tools: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
        finalize_style: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
    ) -> LifecycleContext:
        """
        Convenience method to run the full lifecycle with all phases.

        This is the recommended way for backends to integrate, as it
        ensures the correct phase order and proper before/after hook
        execution for each creation step.

        Args:
            ctx: Initial lifecycle context.
            create_*: Callables that perform the actual backend-specific
                creation for each phase. Each receives and returns the context.
            finalize_style: Callable for final style application.

        Returns:
            The final context after all phases complete.
        """
        ctx = self.run_lifecycle_phase(LifecyclePhase.PRE_INIT, ctx)

        if create_figure:
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_FIGURE, ctx, create_figure)
        else:
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_FIGURE, ctx)

        if create_layout:
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_LAYOUT, ctx, create_layout)
        else:
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_LAYOUT, ctx)

        if create_axes:
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_AXES, ctx, create_axes)
        else:
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_AXES, ctx)

        if create_glyphs:
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_GLYPHS, ctx, create_glyphs)
        else:
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_GLYPHS, ctx)

        if create_legend:
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_LEGEND, ctx, create_legend)
        else:
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_LEGEND, ctx)

        if create_colorbar:
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_COLORBAR, ctx, create_colorbar)
        else:
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_COLORBAR, ctx)

        if create_tools:
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_TOOLS, ctx, create_tools)
        else:
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_TOOLS, ctx)

        if finalize_style:
            ctx = self.run_lifecycle_phase(LifecyclePhase.FINALIZE_STYLE, ctx, finalize_style)
        else:
            ctx = self.run_lifecycle_phase(LifecyclePhase.FINALIZE_STYLE, ctx)

        ctx = self.run_lifecycle_phase(LifecyclePhase.POST_INIT, ctx)

        return ctx


class ThemeHook(LifecycleHook):
    """
    Base class for theme hooks that apply styling across multiple phases.

    Subclasses should override specific phase methods to implement
    backend-specific theme application. By default, theme hooks run
    AFTER each creation phase to modify the created objects.

    The default priority (100) ensures theme hooks run after most
    other hooks but before debug/logging hooks.
    """

    def __init__(self, theme: Any = None, priority: int = 100):
        super().__init__(priority=priority)
        self.theme = theme or {}

    @hook_for(LifecyclePhase.CREATE_FIGURE, when="after")
    def on_create_figure(self, ctx: LifecycleContext) -> LifecycleContext:
        """Apply theme to figure after creation."""
        return self.apply_to_figure(ctx)

    @hook_for(LifecyclePhase.CREATE_AXES, when="after")
    def on_create_axes(self, ctx: LifecycleContext) -> LifecycleContext:
        """Apply theme to axes after creation."""
        return self.apply_to_axes(ctx)

    @hook_for(LifecyclePhase.CREATE_LEGEND, when="after")
    def on_create_legend(self, ctx: LifecycleContext) -> LifecycleContext:
        """Apply theme to legend after creation."""
        return self.apply_to_legend(ctx)

    @hook_for(LifecyclePhase.CREATE_COLORBAR, when="after")
    def on_create_colorbar(self, ctx: LifecycleContext) -> LifecycleContext:
        """Apply theme to colorbar after creation."""
        return self.apply_to_colorbar(ctx)

    @hook_for(LifecyclePhase.FINALIZE_STYLE, when="after")
    def on_finalize_style(self, ctx: LifecycleContext) -> LifecycleContext:
        """Apply final theme touches."""
        return self.apply_final(ctx)

    def apply_to_figure(self, ctx: LifecycleContext) -> LifecycleContext:
        """Override to apply theme to the figure object."""
        return ctx

    def apply_to_axes(self, ctx: LifecycleContext) -> LifecycleContext:
        """Override to apply theme to the axes object(s)."""
        return ctx

    def apply_to_legend(self, ctx: LifecycleContext) -> LifecycleContext:
        """Override to apply theme to the legend object."""
        return ctx

    def apply_to_colorbar(self, ctx: LifecycleContext) -> LifecycleContext:
        """Override to apply theme to the colorbar object."""
        return ctx

    def apply_final(self, ctx: LifecycleContext) -> LifecycleContext:
        """Override for final style application pass."""
        return ctx


class DebugHook(LifecycleHook):
    """
    A debug hook that prints lifecycle phase information.

    Useful for debugging plot initialization issues across backends.
    Can show both "before" and "after" state for creation phases.
    """

    def __init__(
        self,
        log_fn: Optional[Callable[[str], None]] = None,
        phases: Optional[List[LifecyclePhase]] = None,
        show_before: bool = False,
        show_after: bool = True,
        priority: int = 1000,
    ):
        super().__init__(priority=priority)
        self.log_fn = log_fn or print
        self.phases = phases
        self.show_before = show_before
        self.show_after = show_after

    def should_run(self, phase: LifecyclePhase, when: str, ctx: LifecycleContext) -> bool:
        if self.phases is not None and phase not in self.phases:
            return False
        if when == "before" and not self.show_before:
            return False
        if when == "after" and not self.show_after:
            return False
        return True

    @hook_for(LifecyclePhase.PRE_INIT, when="after")
    def log_pre_init(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] PRE_INIT: element={ctx.element}")
        return ctx

    @hook_for(LifecyclePhase.CREATE_FIGURE, when="before")
    def log_create_figure_before(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] CREATE_FIGURE [before]: about to create figure")
        return ctx

    @hook_for(LifecyclePhase.CREATE_FIGURE, when="after")
    def log_create_figure_after(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] CREATE_FIGURE [after]: figure={ctx.figure}")
        return ctx

    @hook_for(LifecyclePhase.CREATE_LAYOUT, when="after")
    def log_create_layout(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] CREATE_LAYOUT: layout={ctx.layout}")
        return ctx

    @hook_for(LifecyclePhase.CREATE_AXES, when="after")
    def log_create_axes(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] CREATE_AXES: axes={ctx.axes}")
        return ctx

    @hook_for(LifecyclePhase.CREATE_GLYPHS, when="after")
    def log_create_glyphs(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] CREATE_GLYPHS: glyphs={ctx.glyphs}")
        return ctx

    @hook_for(LifecyclePhase.CREATE_LEGEND, when="after")
    def log_create_legend(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] CREATE_LEGEND: legend={ctx.legend}")
        return ctx

    @hook_for(LifecyclePhase.CREATE_COLORBAR, when="after")
    def log_create_colorbar(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] CREATE_COLORBAR: colorbar={ctx.colorbar}")
        return ctx

    @hook_for(LifecyclePhase.CREATE_TOOLS, when="after")
    def log_create_tools(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] CREATE_TOOLS: tools={ctx.tools}")
        return ctx

    @hook_for(LifecyclePhase.FINALIZE_STYLE, when="after")
    def log_finalize_style(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] FINALIZE_STYLE")
        return ctx

    @hook_for(LifecyclePhase.POST_INIT, when="after")
    def log_post_init(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] POST_INIT: state={ctx.state}")
        return ctx


__all__ = [
    "LifecyclePhase",
    "LifecycleContext",
    "LifecycleHook",
    "LifecycleMixin",
    "ThemeHook",
    "DebugHook",
    "hook_for",
]
