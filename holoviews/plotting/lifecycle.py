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

    LifecycleHook
        Base class for custom hooks that can be registered to run at
        specific lifecycle phases.

    LifecycleMixin
        Mixin class that provides lifecycle management capabilities to
        backend-specific Plot classes.

Lifecycle Phases (in order):

    1.  pre_init        - Before any plot initialization begins
    2.  create_figure   - Create the figure/canvas
    3.  create_layout   - Create layout/container
    4.  create_axes     - Create axes with labels, ticks, ranges
    5.  create_glyphs   - Create glyphs/artists/traces from data
    6.  create_legend   - Create legend
    7.  create_colorbar - Create colorbar
    8.  create_tools    - Create tools (hover, zoom, pan, etc.)
    9.  finalize_style  - Apply final styling (themes, fonts, etc.)
    10. post_init       - After all initialization is complete

Usage for Backend Integration:

    class MyBackendPlot(LifecycleMixin, BasePlot):
        def initialize_plot(self, ranges=None):
            # Build lifecycle context
            ctx = LifecycleContext(
                plot=self,
                element=self.hmap.last,
                ranges=ranges,
                key=self.keys[-1]
            )

            # Run lifecycle phases in order
            ctx = self.run_lifecycle_phase(LifecyclePhase.PRE_INIT, ctx)
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_FIGURE, ctx)
            # ... backend-specific figure creation using ctx.figure
            ctx = self.run_lifecycle_phase(LifecyclePhase.CREATE_AXES, ctx)
            # ... backend-specific axes creation
            # ... continue through all phases

            return ctx.state

Usage for Custom Hooks:

    class DebugHook(LifecycleHook):
        @hook_for(LifecyclePhase.CREATE_FIGURE)
        def log_figure_creation(self, ctx):
            print(f"Creating figure for {ctx.element}")
            return ctx

    # Register the hook for all plots of a backend
    BokehElementPlot.register_lifecycle_hook(DebugHook())
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
        tools: The tools list (set in CREATE_TOOLS).
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


def hook_for(phase: LifecyclePhase) -> Callable:
    """
    Decorator to mark a method as a hook for a specific lifecycle phase.

    Usage:
        class MyHook(LifecycleHook):
            @hook_for(LifecyclePhase.CREATE_FIGURE)
            def on_create_figure(self, ctx):
                # ...
                return ctx
    """

    def decorator(func: Callable) -> Callable:
        func._lifecycle_phase = phase
        return func

    return decorator


class LifecycleHook:
    """
    Base class for lifecycle hooks.

    Subclasses should define methods decorated with @hook_for to handle
    specific lifecycle phases. Hook methods receive a LifecycleContext
    and must return it (possibly modified).

    A hook can also implement `should_run` to conditionally skip execution.
    """

    priority: int = 0

    def __init__(self, priority: int = 0):
        self.priority = priority
        self._phase_handlers: Dict[LifecyclePhase, Callable] = {}
        self._discover_phase_handlers()

    def _discover_phase_handlers(self) -> None:
        """Discover methods decorated with @hook_for."""
        for _, method in inspect.getmembers(self, predicate=inspect.ismethod):
            phase = getattr(method, "_lifecycle_phase", None)
            if phase is not None:
                self._phase_handlers[phase] = method

    def should_run(self, phase: LifecyclePhase, ctx: LifecycleContext) -> bool:
        """
        Determine if this hook should run for the given phase and context.

        Override to add conditional logic.
        """
        return phase in self._phase_handlers

    def run(self, phase: LifecyclePhase, ctx: LifecycleContext) -> LifecycleContext:
        """Run the hook for the given phase if applicable."""
        if not self.should_run(phase, ctx):
            return ctx
        handler = self._phase_handlers.get(phase)
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

    Class-level hooks apply to all instances. Instance-level hooks
    apply only to that instance.

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
        self, phase: LifecyclePhase, ctx: LifecycleContext
    ) -> LifecycleContext:
        """
        Run all applicable hooks for a given lifecycle phase.

        This method should be called by the backend's initialize_plot
        method at the appropriate point in the initialization process.

        Args:
            phase: The current lifecycle phase.
            ctx: The lifecycle context.

        Returns:
            The (possibly modified) context.
        """
        self._current_lifecycle_phase = phase

        for hook in self._get_all_hooks():
            if hook.should_run(phase, ctx):
                ctx = hook.run(phase, ctx)

        return ctx

    @property
    def current_lifecycle_phase(self) -> Optional[LifecyclePhase]:
        """Get the currently executing lifecycle phase."""
        return self._current_lifecycle_phase

    def run_full_lifecycle(
        self,
        ctx: LifecycleContext,
        backend_create_figure: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
        backend_create_layout: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
        backend_create_axes: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
        backend_create_glyphs: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
        backend_create_legend: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
        backend_create_colorbar: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
        backend_create_tools: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
        backend_finalize_style: Optional[Callable[[LifecycleContext], LifecycleContext]] = None,
    ) -> LifecycleContext:
        """
        Convenience method to run the full lifecycle with backend-specific
        creation callbacks inserted between hook executions.

        This is useful for backends that want a structured way to run
        their initialization code while still allowing hooks to intercept
        at each phase.

        Args:
            ctx: Initial lifecycle context.
            backend_*: Callables that perform the actual backend-specific
                creation for each phase. Each receives and returns the context.

        Returns:
            The final context after all phases complete.
        """
        phase_callbacks = {
            LifecyclePhase.PRE_INIT: None,
            LifecyclePhase.CREATE_FIGURE: backend_create_figure,
            LifecyclePhase.CREATE_LAYOUT: backend_create_layout,
            LifecyclePhase.CREATE_AXES: backend_create_axes,
            LifecyclePhase.CREATE_GLYPHS: backend_create_glyphs,
            LifecyclePhase.CREATE_LEGEND: backend_create_legend,
            LifecyclePhase.CREATE_COLORBAR: backend_create_colorbar,
            LifecyclePhase.CREATE_TOOLS: backend_create_tools,
            LifecyclePhase.FINALIZE_STYLE: backend_finalize_style,
            LifecyclePhase.POST_INIT: None,
        }

        for phase in LifecyclePhase.all_phases():
            ctx = self.run_lifecycle_phase(phase, ctx)
            callback = phase_callbacks.get(phase)
            if callback is not None:
                ctx = callback(ctx)

        return ctx


class ThemeHook(LifecycleHook):
    """
    Base class for theme hooks that apply styling at the FINALIZE_STYLE phase.

    Subclasses should override `apply_theme` to implement backend-specific
    theme application.
    """

    def __init__(self, theme: Any, priority: int = 100):
        super().__init__(priority=priority)
        self.theme = theme

    @hook_for(LifecyclePhase.FINALIZE_STYLE)
    def apply_theme_hook(self, ctx: LifecycleContext) -> LifecycleContext:
        return self.apply_theme(ctx)

    def apply_theme(self, ctx: LifecycleContext) -> LifecycleContext:
        """Override in subclasses to apply the theme."""
        return ctx


class DebugHook(LifecycleHook):
    """
    A debug hook that prints lifecycle phase information.

    Useful for debugging plot initialization issues across backends.
    """

    def __init__(
        self,
        log_fn: Optional[Callable[[str], None]] = None,
        phases: Optional[List[LifecyclePhase]] = None,
        priority: int = 1000,
    ):
        super().__init__(priority=priority)
        self.log_fn = log_fn or print
        self.phases = phases

    def should_run(self, phase: LifecyclePhase, ctx: LifecycleContext) -> bool:
        if self.phases is None:
            return True
        return phase in self.phases

    @hook_for(LifecyclePhase.PRE_INIT)
    def log_pre_init(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] Starting initialization for {ctx.element}")
        return ctx

    @hook_for(LifecyclePhase.CREATE_FIGURE)
    def log_create_figure(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] CREATE_FIGURE: figure={ctx.figure}")
        return ctx

    @hook_for(LifecyclePhase.CREATE_AXES)
    def log_create_axes(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] CREATE_AXES: axes={ctx.axes}")
        return ctx

    @hook_for(LifecyclePhase.CREATE_GLYPHS)
    def log_create_glyphs(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] CREATE_GLYPHS: glyphs={ctx.glyphs}")
        return ctx

    @hook_for(LifecyclePhase.CREATE_LEGEND)
    def log_create_legend(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] CREATE_LEGEND: legend={ctx.legend}")
        return ctx

    @hook_for(LifecyclePhase.CREATE_COLORBAR)
    def log_create_colorbar(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] CREATE_COLORBAR: colorbar={ctx.colorbar}")
        return ctx

    @hook_for(LifecyclePhase.CREATE_TOOLS)
    def log_create_tools(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] CREATE_TOOLS: tools={ctx.tools}")
        return ctx

    @hook_for(LifecyclePhase.POST_INIT)
    def log_post_init(self, ctx: LifecycleContext) -> LifecycleContext:
        self.log_fn(f"[Lifecycle] Initialization complete for {ctx.element}")
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
