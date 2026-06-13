"""Unified render artifact manager for HoloViews.

Centralizes the management of renderer output artifacts.  Artifacts are
organized into four mutually exclusive **ownership categories** that
define distinct release semantics:

1. ``TEMPORARY`` — Scratch artifacts created during a single render
   pass (e.g. temporary files, BytesIO/StringIO buffers).  These are
   **always** eligible for cleanup when their owning scope exits, and
   are aggressively released by ``release_all()``.

2. ``USER_OUTPUT`` — Files and MIME bundles that are intended to be
   returned to the user (e.g. ``save()`` output, notebook display
   payloads).  These are **never** released by ``release_all()``
   unless explicitly forced with ``force=True``.

3. ``EXTERNAL_OBJECT`` — Backend objects whose lifetime is managed by
   an external framework (Bokeh Document, Matplotlib Figure, Panel
   Viewable, Plotly Figure, etc.).  These have backend-specific
   release handlers that properly tear down callbacks, sessions, and
   widget references.

4. ``CACHE`` — Intermediate computation results cached for reuse
   across render cycles (e.g. tight bounding boxes, compiled plot
   objects).  Managed via LRU eviction.

This module provides:
1. ``ArtifactCategory``: Top-level ownership classification
2. ``ArtifactKind``: Specific kind within a category
3. ``CleanupPolicy``: When to auto-release
4. ``RenderArtifact``: Dataclass representing one artifact
5. ``ArtifactScope``: Context-manager grouping artifacts
6. ``RenderArtifactManager``: Central registry, factory and cleaner
7. Module-level singleton ``artifact_manager`` for global use
"""

from __future__ import annotations

import atexit
import gc
import os
import shutil
import sys
import tempfile
import time
import traceback
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO, StringIO
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    FrozenSet,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

if TYPE_CHECKING:
    from types import TracebackType


# Sentinel for internal use — distinguished from None which is a valid cache value
_SENTINEL = object()


# ---------------------------------------------------------------------------
# Top-level ownership categories
# ---------------------------------------------------------------------------


class ArtifactCategory(str, Enum):
    """Top-level ownership classification defining release semantics."""

    TEMPORARY = "temporary"
    USER_OUTPUT = "user_output"
    EXTERNAL_OBJECT = "external_object"
    CACHE = "cache"


# ---------------------------------------------------------------------------
# Artifact type enumeration with category mapping
# ---------------------------------------------------------------------------


class ArtifactKind(str, Enum):
    """Specific kind of a render artifact, within a category."""

    # --- TEMPORARY ---
    FILE_TEMP = "file_temp"
    DIR_TEMP = "dir_temp"
    BUFFER_BYTES = "buffer_bytes"
    BUFFER_STRING = "buffer_string"

    # --- USER_OUTPUT ---
    FILE_OUTPUT = "file_output"       # save() to user-controlled path
    DATA_OUTPUT = "data_output"       # final data returned to caller
    MIME_OUTPUT = "mime_output"       # notebook MIME bundle payload

    # --- EXTERNAL_OBJECT ---
    BOKEH_DOCUMENT = "bokeh_document"
    BOKEH_MODEL = "bokeh_model"
    MPL_FIGURE = "mpl_figure"
    PLOTLY_FIGURE = "plotly_figure"
    PANEL_VIEWABLE = "panel_viewable"

    # --- CACHE ---
    CACHE_ENTRY = "cache_entry"
    PLOT_REGISTRY = "plot_registry"   # plot object in Renderer._plots
    PLOTLY_JSON = "plotly_json"

    # --- Legacy / transitional kinds retained for BC ---
    DATA_BYTES = "data_bytes"
    DATA_STR = "data_str"
    DATA_MIME = "data_mime"

    # --- Fallback ---
    OTHER = "other"

    # --- Category membership sets ---
    _TEMPORARY_KINDS: FrozenSet["ArtifactKind"] = frozenset({
        FILE_TEMP, DIR_TEMP, BUFFER_BYTES, BUFFER_STRING,
    })
    _USER_OUTPUT_KINDS: FrozenSet["ArtifactKind"] = frozenset({
        FILE_OUTPUT, DATA_OUTPUT, MIME_OUTPUT,
    })
    _EXTERNAL_KINDS: FrozenSet["ArtifactKind"] = frozenset({
        BOKEH_DOCUMENT, BOKEH_MODEL, MPL_FIGURE,
        PLOTLY_FIGURE, PANEL_VIEWABLE,
    })
    _CACHE_KINDS: FrozenSet["ArtifactKind"] = frozenset({
        CACHE_ENTRY, PLOT_REGISTRY, PLOTLY_JSON,
    })
    _TRANSITIONAL_KINDS: FrozenSet["ArtifactKind"] = frozenset({
        DATA_BYTES, DATA_STR, DATA_MIME,
    })

    @property
    def category(self) -> ArtifactCategory:
        """Return the ownership category of this kind."""
        if self in self._TEMPORARY_KINDS:
            return ArtifactCategory.TEMPORARY
        if self in self._USER_OUTPUT_KINDS:
            return ArtifactCategory.USER_OUTPUT
        if self in self._EXTERNAL_KINDS:
            return ArtifactCategory.EXTERNAL_OBJECT
        if self in self._CACHE_KINDS:
            return ArtifactCategory.CACHE
        if self in self._TRANSITIONAL_KINDS:
            return ArtifactCategory.TEMPORARY  # transitional -> temp
        return ArtifactCategory.TEMPORARY


# ---------------------------------------------------------------------------
# Cleanup policy enumeration
# ---------------------------------------------------------------------------


class CleanupPolicy(str, Enum):
    """When to automatically clean up an artifact."""

    # Clean up when the owning scope exits
    SCOPE_EXIT = "scope_exit"

    # Clean up when a new render cycle starts (last-N retention)
    RENDER_CYCLE = "render_cycle"

    # Clean up at interpreter exit (atexit)
    INTERPRETER_EXIT = "interpreter_exit"

    # Never auto-clean; user must call release() explicitly
    MANUAL = "manual"


# ---------------------------------------------------------------------------
# Artifact dataclass
# ---------------------------------------------------------------------------


@dataclass
class RenderArtifact:
    """Represents a single render artifact tracked by the manager.

    Attributes
    ----------
    id : str
        Globally unique identifier for the artifact.
    kind : ArtifactKind
        Classification of the artifact.
    scope_id : str
        The scope this artifact belongs to.
    owner : Optional[str]
        A label describing who created the artifact (e.g. renderer class,
        display hook name).  Useful for debugging.
    obj : Any
        The actual artifact payload.  May be ``None`` for filesystem
        artifacts where only the path is relevant.
    path : Optional[str]
        Filesystem path, if applicable.
    refs : Dict[str, Any]
        Arbitrary reference metadata (e.g. parent plot id, format string).
    policy : CleanupPolicy
        Automatic cleanup policy.
    created_at : float
        POSIX timestamp of creation.
    size_bytes : Optional[int]
        Payload size if computable (file size, bytes length, etc.).
    format : Optional[str]
        Render format hint (e.g. ``"png"``, ``"html"``, ``"mimebundle"``).
    stack : Optional[str]
        Traceback (as string) of the creation call site; captured when
        ``debug=True`` on the manager.
    _cleanup_fn : Optional[Callable[["RenderArtifact"], None]]
        Optional custom cleanup callable.  Invoked with the artifact
        instance during ``release()``.  Should be idempotent.
    _released : bool
        Whether ``release()`` has already been called.
    """

    id: str
    kind: ArtifactKind
    scope_id: str
    owner: Optional[str] = None
    obj: Any = None
    path: Optional[str] = None
    refs: Dict[str, Any] = field(default_factory=dict)
    policy: CleanupPolicy = CleanupPolicy.SCOPE_EXIT
    created_at: float = field(default_factory=time.time)
    size_bytes: Optional[int] = None
    format: Optional[str] = None
    stack: Optional[str] = None
    _cleanup_fn: Optional[Callable[["RenderArtifact"], None]] = None
    _released: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def category(self) -> ArtifactCategory:
        """The ownership category of this artifact, derived from its kind."""
        return self.kind.category

    @property
    def released(self) -> bool:
        return self._released

    @property
    def age(self) -> float:
        """Age of this artifact in seconds."""
        return time.time() - self.created_at

    def release(self, force: bool = False) -> bool:
        """Release (clean up) this artifact.

        Idempotent: calling on an already-released artifact is a no-op
        and returns ``False``.

        Returns
        -------
        bool
            ``True`` if cleanup was actually performed this call.
        """
        if self._released and not force:
            return False
        try:
            self._do_release()
        finally:
            self._released = True
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _do_release(self) -> None:
        # ---- USER_OUTPUT: register-only, never destroy ----
        # These artifacts belong to the caller.  Releasing them only
        # drops our tracking reference; we NEVER unlink user files,
        # mutate user data, or clear content.  This applies even when
        # include_user_output=True is passed to release_all().
        if self.category == ArtifactCategory.USER_OUTPUT:
            self.obj = None
            # path intentionally NOT removed for FILE_OUTPUT
            return

        if self._cleanup_fn is not None:
            try:
                self._cleanup_fn(self)
            except Exception:  # noqa: BLE001
                _log_warning(f"Custom cleanup failed for artifact {self.id}")
            return

        if self.kind in (ArtifactKind.FILE_TEMP, ArtifactKind.DIR_TEMP):
            if self.path and os.path.exists(self.path):
                try:
                    if self.kind == ArtifactKind.FILE_TEMP:
                        os.remove(self.path)
                    else:
                        shutil.rmtree(self.path, ignore_errors=True)
                except Exception:  # noqa: BLE001
                    _log_warning(f"Failed to remove artifact path: {self.path}")
            return

        if self.kind in (ArtifactKind.BUFFER_BYTES, ArtifactKind.BUFFER_STRING):
            if isinstance(self.obj, (BytesIO, StringIO)):
                try:
                    self.obj.close()
                except Exception:  # noqa: BLE001
                    pass
            return

        if self.kind in _backend_handlers():
            try:
                _backend_handlers()[self.kind](self)
            except Exception:  # noqa: BLE001
                _log_warning(f"Backend handler failed for {self.kind}, art {self.id}")
            finally:
                self.obj = None
            return

        # Default: drop reference
        self.obj = None


# ---------------------------------------------------------------------------
# Lightweight logger (avoids circular imports at module level)
# ---------------------------------------------------------------------------

def _log_warning(msg: str) -> None:
    try:
        import param

        param.main.param.warning(f"[RenderArtifactManager] {msg}")
    except Exception:  # noqa: BLE001
        print(f"[RenderArtifactManager] WARNING: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Backend-specific release handlers
# ---------------------------------------------------------------------------


def _release_bokeh_document(art: RenderArtifact) -> None:
    """Release a Bokeh Document: remove roots, clear session callbacks,
    destroy models.

    This properly tears down the Bokeh object graph so it can be GC'd.
    ONLY proceeds if the artifact's ``source`` is NOT ``"user"`` — we
    never mutate documents that belong to user code.
    """
    if art.obj is None:
        return
    source = art.refs.get("source", "renderer")
    if source == "user":
        art.obj = None
        return
    doc = art.obj
    try:
        try:
            from bokeh.document import Document
            is_bokeh_doc = isinstance(doc, Document)
        except Exception:  # noqa: BLE001
            is_bokeh_doc = False

        if is_bokeh_doc:
            for root in list(doc.roots):
                try:
                    doc.remove_root(root)
                except Exception:  # noqa: BLE001
                    pass
            for cb in list(getattr(doc, "session_callbacks", [])):
                try:
                    doc.remove_session_callback(cb)
                except Exception:  # noqa: BLE001
                    pass
            session = getattr(doc, "_session", None)
            if session is not None:
                for cb in list(getattr(session, "_callbacks", {})):
                    try:
                        session.remove_timeout(cb)
                    except Exception:  # noqa: BLE001
                        pass
            for sub in list(getattr(doc, "_subscribed_events", [])):
                try:
                    doc.unsubscribe(sub)
                except Exception:  # noqa: BLE001
                    pass
            try:
                doc.clear()
            except Exception:  # noqa: BLE001
                pass
        else:
            # Not a real Bokeh Document — try duck-typed cleanup so
            # that fake objects / test doubles still get their clear()
            # method called, respecting source protection.
            for root in list(getattr(doc, "roots", [])):
                try:
                    doc.remove_root(root)
                except Exception:  # noqa: BLE001
                    pass
            try:
                doc.clear()
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        art.obj = None


def _release_bokeh_model(art: RenderArtifact) -> None:
    """Release a Bokeh Model: clear callbacks and references so it can be GC'd.

    Respects the ``source`` ref: user-owned models are left untouched.
    """
    if art.obj is None:
        return
    source = art.refs.get("source", "renderer")
    if source == "user":
        art.obj = None
        return
    model = art.obj
    try:
        # Remove all references from the model
        if hasattr(model, "_document"):
            model._document = None
        if hasattr(model, "_callbacks"):
            try:
                model._callbacks.clear()
            except Exception:  # noqa: BLE001
                pass
        if hasattr(model, "js_property_callbacks"):
            try:
                model.js_property_callbacks.clear()
            except Exception:  # noqa: BLE001
                pass
        if hasattr(model, "js_event_callbacks"):
            try:
                model.js_event_callbacks.clear()
            except Exception:  # noqa: BLE001
                pass
        # Drop references to sub-models
        if hasattr(model, "properties_with_refs"):
            for prop in model.properties_with_refs():
                try:
                    setattr(model, prop, None)
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        art.obj = None


def _release_mpl_figure(art: RenderArtifact) -> None:
    """Release a Matplotlib Figure via plt.close() and clear its contents.

    Also clear axes and references so the figure can be garbage collected,
    preventing Matplotlib's global figure registry no longer keeps it
    alive.  Respects ``source == "user"`` — never close figures that
    user code may still be using.
    """
    if art.obj is None:
        return
    source = art.refs.get("source", "renderer")
    if source == "user":
        art.obj = None
        return
    fig = art.obj
    try:
        import matplotlib.pyplot as plt

        try:
            for ax in list(fig.axes):
                try:
                    ax.cla()
                    ax.clear()
                except Exception:  # noqa: BLE001
                    pass
            try:
                fig.clf()
            except Exception:  # noqa: BLE001
                pass
            try:
                fig._axstack.clear()
            except Exception:  # noqa: BLE001
                pass
            try:
                fig._cachedRenderer = None
            except Exception:  # noqa: BLE001
                pass
            try:
                plt.close(fig)
            except Exception:  # noqa: BLE001
                pass
            # Also attempt to close by number if it was registered
            try:
                if hasattr(fig, "number") and fig.number is not None:
                    try:
                        plt.close(fig.number)
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
    finally:
        art.obj = None


def _release_plotly_figure(art: RenderArtifact) -> None:
    """Release a Plotly Figure: clear data and references so it can be GC'd.

    Respects ``source == "user"`` — user-owned figures are left intact.
    """
    if art.obj is None:
        return
    source = art.refs.get("source", "renderer")
    if source == "user":
        art.obj = None
        return
    fig = art.obj
    try:
        # Plotly figures can keep references to data arrays; clear them
        if hasattr(fig, "data"):
            try:
                fig.data = []
            except Exception:  # noqa: BLE001
                pass
        if hasattr(fig, "_data_objs"):
            try:
                fig._data_objs = []
            except Exception:  # noqa: BLE001
                pass
        if hasattr(fig, "_plotlyjs_version"):
            try:
                del fig._plotlyjs_version
            except Exception:  # noqa: BLE001
                pass
        # Clear the frame data
        if hasattr(fig, "frames"):
            try:
                fig.frames = []
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        art.obj = None


def _release_panel_viewable(art: RenderArtifact) -> None:
    """Release a Panel Viewable / widget: clear model references,
    callbacks and comms.

    Panel objects can hold references to plots, documents, and comms
    that prevent garbage collection.  Respects ``source == "user"``.
    """
    if art.obj is None:
        return
    source = art.refs.get("source", "renderer")
    if source == "user":
        art.obj = None
        return
    viewable = art.obj
    try:
        # Stop any running servers or watchers
        if hasattr(viewable, "_cleanup"):
            try:
                viewable._cleanup()
            except Exception:  # noqa: BLE001
                pass
        if hasattr(viewable, "cleanup"):
            try:
                viewable.cleanup()
            except Exception:  # noqa: BLE001
                pass
        # Clear param watchers
        if hasattr(viewable, "_watchers"):
            try:
                for pname in list(viewable._watchers.keys()):
                    for w in list(viewable._watchers[pname]):
                        try:
                            viewable.unwatch(w)
                        except Exception:  # noqa: BLE001
                            pass
            except Exception:  # noqa: BLE001
                pass
        # Drop internal references
        if hasattr(viewable, "_models"):
            try:
                viewable._models = {}
            except Exception:  # noqa: BLE001
                pass
        if hasattr(viewable, "_comms"):
            try:
                for comm in list(viewable._comms.values()):
                    try:
                        if hasattr(comm, "close"):
                            comm.close()
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:  # noqa: BLE001
                pass
        if hasattr(viewable, "_layout"):
            try:
                viewable._layout = None
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        art.obj = None


# Map ArtifactKind -> backend release handler, populated lazily
# to avoid definition-order issues with RenderArtifact._do_release
_BACKEND_HANDLERS: Optional[Dict[ArtifactKind, Callable[[RenderArtifact], None]]] = None


def _backend_handlers() -> Dict[ArtifactKind, Callable[[RenderArtifact], None]]:
    """Lazily-initialized backend handler registry.

    This allows ``RenderArtifact._do_release`` to reference the
    handlers even though the handler functions are defined later in
    the module.
    """
    global _BACKEND_HANDLERS
    if _BACKEND_HANDLERS is None:
        _BACKEND_HANDLERS = {
            ArtifactKind.BOKEH_DOCUMENT: _release_bokeh_document,
            ArtifactKind.BOKEH_MODEL: _release_bokeh_model,
            ArtifactKind.MPL_FIGURE: _release_mpl_figure,
            ArtifactKind.PLOTLY_FIGURE: _release_plotly_figure,
            ArtifactKind.PANEL_VIEWABLE: _release_panel_viewable,
        }
    return _BACKEND_HANDLERS


# ---------------------------------------------------------------------------
# ArtifactScope: context manager
# ---------------------------------------------------------------------------


class ArtifactScope:
    """Context manager that groups artifacts under a single scope id.

    Upon exiting the context (including via exception), all artifacts
    with ``CleanupPolicy.SCOPE_EXIT`` that were registered to this
    scope are released.
    """

    def __init__(
        self,
        manager: "RenderArtifactManager",
        scope_id: str,
        owner: Optional[str] = None,
    ) -> None:
        self._manager = manager
        self.scope_id = scope_id
        self.owner = owner
        self._exited = False

    # ------------------------------------------------------------------
    # Registration shortcuts
    # ------------------------------------------------------------------

    def register(self, *args: Any, **kwargs: Any) -> RenderArtifact:
        kwargs.setdefault("scope_id", self.scope_id)
        kwargs.setdefault("owner", self.owner)
        return self._manager.register(*args, **kwargs)

    def register_data(self, *args: Any, **kwargs: Any) -> RenderArtifact:
        kwargs.setdefault("scope_id", self.scope_id)
        kwargs.setdefault("owner", self.owner)
        return self._manager.register_data(*args, **kwargs)

    def register_output_data(self, *args: Any, **kwargs: Any) -> RenderArtifact:
        kwargs.setdefault("scope_id", self.scope_id)
        kwargs.setdefault("owner", self.owner)
        return self._manager.register_output_data(*args, **kwargs)

    def register_output_file(self, *args: Any, **kwargs: Any) -> RenderArtifact:
        kwargs.setdefault("scope_id", self.scope_id)
        kwargs.setdefault("owner", self.owner)
        return self._manager.register_output_file(*args, **kwargs)

    def register_output_mime(self, *args: Any, **kwargs: Any) -> RenderArtifact:
        kwargs.setdefault("scope_id", self.scope_id)
        kwargs.setdefault("owner", self.owner)
        return self._manager.register_output_mime(*args, **kwargs)

    def register_external_object(self, *args: Any, **kwargs: Any) -> RenderArtifact:
        kwargs.setdefault("scope_id", self.scope_id)
        kwargs.setdefault("owner", self.owner)
        return self._manager.register_external_object(*args, **kwargs)

    def create_tempfile(self, *args: Any, **kwargs: Any) -> Tuple[RenderArtifact, IO]:
        kwargs.setdefault("scope_id", self.scope_id)
        kwargs.setdefault("owner", self.owner)
        return self._manager.create_tempfile(*args, **kwargs)

    def create_tempdir(self, *args: Any, **kwargs: Any) -> Tuple[RenderArtifact, str]:
        kwargs.setdefault("scope_id", self.scope_id)
        kwargs.setdefault("owner", self.owner)
        return self._manager.create_tempdir(*args, **kwargs)

    def create_bytesio(self, *args: Any, **kwargs: Any) -> Tuple[RenderArtifact, BytesIO]:
        kwargs.setdefault("scope_id", self.scope_id)
        kwargs.setdefault("owner", self.owner)
        return self._manager.create_bytesio(*args, **kwargs)

    def create_stringio(self, *args: Any, **kwargs: Any) -> Tuple[RenderArtifact, StringIO]:
        kwargs.setdefault("scope_id", self.scope_id)
        kwargs.setdefault("owner", self.owner)
        return self._manager.create_stringio(*args, **kwargs)

    def cache_put(self, *args: Any, **kwargs: Any) -> RenderArtifact:
        kwargs.setdefault("scope_id", self.scope_id)
        kwargs.setdefault("owner", self.owner)
        return self._manager.cache_put(*args, **kwargs)

    def cache_get(self, *args: Any, **kwargs: Any) -> Any:
        return self._manager.cache_get(*args, **kwargs)

    def cache_has(self, *args: Any, **kwargs: Any) -> bool:
        return self._manager.cache_has(*args, **kwargs)

    def cache_pop(self, *args: Any, **kwargs: Any) -> Any:
        return self._manager.cache_pop(*args, **kwargs)

    def cache_delete(self, *args: Any, **kwargs: Any) -> bool:
        return self._manager.cache_delete(*args, **kwargs)

    def cache_clear(self) -> int:
        return self._manager.cache_clear()

    def list_artifacts(self, **kwargs: Any) -> List[RenderArtifact]:
        kwargs.setdefault("scope_id", self.scope_id)
        return self._manager.list_artifacts(**kwargs)

    def release(
        self,
        policy: Optional[CleanupPolicy] = None,
        include_user_output: bool = False,
        categories: Optional[Iterable[Union[str, ArtifactCategory]]] = None,
    ) -> int:
        return self._manager.release_scope(
            self.scope_id,
            policy=policy,
            include_user_output=include_user_output,
            categories=categories,
        )

    # ------------------------------------------------------------------
    # Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "ArtifactScope":
        self._manager._push_scope(self.scope_id)
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional["TracebackType"],
    ) -> None:
        self._manager._pop_scope(self.scope_id)
        if not self._exited:
            self._manager.release_scope(
                self.scope_id,
                policy=CleanupPolicy.SCOPE_EXIT,
            )
            self._exited = True


# ---------------------------------------------------------------------------
# RenderArtifactManager
# ---------------------------------------------------------------------------


class RenderArtifactManager:
    """Central registry and factory for render artifacts.

    Typical usage::

        from holoviews.plotting.artifact_manager import artifact_manager

        with artifact_manager.scope("my_render") as scope:
            art, buf = scope.create_bytesio(format="png")
            # ... use buf, it will be closed on scope exit
    """

    # Maximum entries retained by default for RENDER_CYCLE policy
    DEFAULT_CYCLE_RETENTION = 5

    # Maximum entries in the global LRU cache (cache_put / cache_get)
    DEFAULT_CACHE_MAX = 256

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        debug: bool = False,
        cycle_retention: int = DEFAULT_CYCLE_RETENTION,
        cache_max: int = DEFAULT_CACHE_MAX,
    ) -> None:
        self.debug = debug
        self.cycle_retention = max(1, int(cycle_retention))
        self.cache_max = max(1, int(cache_max))

        # All registered artifacts keyed by artifact id
        self._artifacts: "OrderedDict[str, RenderArtifact]" = OrderedDict()

        # Artifact ids grouped by scope id
        self._by_scope: Dict[str, Set[str]] = {}

        # Stack of currently active scope ids (for nested scopes)
        self._active_scopes: List[str] = []

        # Global LRU-style cache: key -> artifact_id
        self._cache: "OrderedDict[Any, str]" = OrderedDict()

        # Render-cycle history (scope ids, most recent last)
        self._cycle_history: List[str] = []

        # Owner label used when none is supplied
        self._default_owner: Optional[str] = None

        atexit.register(self._atexit_cleanup)

    # ------------------------------------------------------------------
    # Default owner
    # ------------------------------------------------------------------

    @contextmanager
    def default_owner(self, owner: str):
        """Context manager to set the default owner label."""
        prev = self._default_owner
        self._default_owner = owner
        try:
            yield
        finally:
            self._default_owner = prev

    # ------------------------------------------------------------------
    # Scope management
    # ------------------------------------------------------------------

    def scope(
        self,
        scope_id: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> ArtifactScope:
        """Return a new ``ArtifactScope`` context manager.

        Parameters
        ----------
        scope_id : str, optional
            Identifier for the scope.  Auto-generated if not provided.
        owner : str, optional
            Default owner label for artifacts created within this scope.
        """
        if scope_id is None:
            scope_id = f"render-{uuid.uuid4().hex[:12]}"
        if scope_id not in self._by_scope:
            self._by_scope[scope_id] = set()
        return ArtifactScope(self, scope_id, owner=owner or self._default_owner)

    def _push_scope(self, scope_id: str) -> None:
        self._active_scopes.append(scope_id)

    def _pop_scope(self, scope_id: str) -> None:
        if self._active_scopes and self._active_scopes[-1] == scope_id:
            self._active_scopes.pop()
        else:
            try:
                self._active_scopes.remove(scope_id)
            except ValueError:
                pass

    @property
    def active_scope_id(self) -> Optional[str]:
        return self._active_scopes[-1] if self._active_scopes else None

    # ------------------------------------------------------------------
    # Core registration
    # ------------------------------------------------------------------

    def register(
        self,
        kind: Union[str, ArtifactKind],
        obj: Any = None,
        *,
        scope_id: Optional[str] = None,
        owner: Optional[str] = None,
        path: Optional[str] = None,
        refs: Optional[Dict[str, Any]] = None,
        policy: Union[str, CleanupPolicy] = CleanupPolicy.SCOPE_EXIT,
        size_bytes: Optional[int] = None,
        format: Optional[str] = None,  # noqa: A002
        cleanup_fn: Optional[Callable[[RenderArtifact], None]] = None,
        artifact_id: Optional[str] = None,
    ) -> RenderArtifact:
        """Register a new artifact and return it.

        The artifact is inserted into the registry and associated with
        the supplied (or currently active) scope.
        """
        kind = ArtifactKind(kind) if isinstance(kind, str) else kind
        policy = CleanupPolicy(policy) if isinstance(policy, str) else policy

        if scope_id is None:
            scope_id = self.active_scope_id
        if scope_id is None:
            scope_id = f"global-{uuid.uuid4().hex[:8]}"
        if scope_id not in self._by_scope:
            self._by_scope[scope_id] = set()

        if artifact_id is None:
            artifact_id = f"art-{uuid.uuid4().hex}"

        stack: Optional[str] = None
        if self.debug:
            stack = "".join(traceback.format_stack()[:-1])

        if size_bytes is None:
            size_bytes = self._estimate_size(obj, path, kind)

        artifact = RenderArtifact(
            id=artifact_id,
            kind=kind,
            scope_id=scope_id,
            owner=owner or self._default_owner,
            obj=obj,
            path=path,
            refs=dict(refs) if refs else {},
            policy=policy,
            size_bytes=size_bytes,
            format=format,
            stack=stack,
            _cleanup_fn=cleanup_fn,
        )

        self._artifacts[artifact_id] = artifact
        self._by_scope[scope_id].add(artifact_id)
        return artifact

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    def create_tempfile(
        self,
        suffix: Optional[str] = None,
        prefix: Optional[str] = "hv_",
        dir: Optional[str] = None,  # noqa: A002
        delete_on_exit: bool = True,
        *,
        scope_id: Optional[str] = None,
        owner: Optional[str] = None,
        policy: Union[str, CleanupPolicy] = CleanupPolicy.SCOPE_EXIT,
        format: Optional[str] = None,  # noqa: A002
        refs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[RenderArtifact, IO]:
        """Create a temporary file and register it.

        Returns ``(artifact, file_object)``.
        """
        suffix = f".{format}" if (format and suffix is None) else suffix
        fileobj = tempfile.NamedTemporaryFile(
            suffix=suffix or "",
            prefix=prefix or "hv_",
            dir=dir,
            delete=False,
        )
        artifact = self.register(
            ArtifactKind.FILE_TEMP,
            obj=fileobj,
            scope_id=scope_id,
            owner=owner,
            path=fileobj.name,
            refs=refs,
            policy=policy if delete_on_exit else CleanupPolicy.MANUAL,
            format=format,
        )
        return artifact, fileobj

    def create_tempdir(
        self,
        suffix: Optional[str] = None,
        prefix: Optional[str] = "hv_",
        dir: Optional[str] = None,  # noqa: A002
        *,
        scope_id: Optional[str] = None,
        owner: Optional[str] = None,
        policy: Union[str, CleanupPolicy] = CleanupPolicy.SCOPE_EXIT,
        refs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[RenderArtifact, str]:
        """Create a temporary directory and register it.

        Returns ``(artifact, dir_path)``.
        """
        path = tempfile.mkdtemp(suffix=suffix or "", prefix=prefix or "hv_", dir=dir)
        artifact = self.register(
            ArtifactKind.DIR_TEMP,
            scope_id=scope_id,
            owner=owner,
            path=path,
            refs=refs,
            policy=policy,
        )
        return artifact, path

    def create_bytesio(
        self,
        initial_bytes: Optional[bytes] = None,
        *,
        scope_id: Optional[str] = None,
        owner: Optional[str] = None,
        policy: Union[str, CleanupPolicy] = CleanupPolicy.SCOPE_EXIT,
        format: Optional[str] = None,  # noqa: A002
        refs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[RenderArtifact, BytesIO]:
        """Create a ``BytesIO`` buffer and register it."""
        buf = BytesIO(initial_bytes) if initial_bytes is not None else BytesIO()
        artifact = self.register(
            ArtifactKind.BUFFER_BYTES,
            obj=buf,
            scope_id=scope_id,
            owner=owner,
            refs=refs,
            policy=policy,
            format=format,
        )
        return artifact, buf

    def create_stringio(
        self,
        initial_value: Optional[str] = None,
        *,
        scope_id: Optional[str] = None,
        owner: Optional[str] = None,
        policy: Union[str, CleanupPolicy] = CleanupPolicy.SCOPE_EXIT,
        format: Optional[str] = None,  # noqa: A002
        refs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[RenderArtifact, StringIO]:
        """Create a ``StringIO`` buffer and register it."""
        buf = StringIO(initial_value) if initial_value is not None else StringIO()
        artifact = self.register(
            ArtifactKind.BUFFER_STRING,
            obj=buf,
            scope_id=scope_id,
            owner=owner,
            refs=refs,
            policy=policy,
            format=format,
        )
        return artifact, buf

    def register_data(
        self,
        data: Union[bytes, str, Dict[str, Any]],
        *,
        scope_id: Optional[str] = None,
        owner: Optional[str] = None,
        policy: Union[str, CleanupPolicy] = CleanupPolicy.SCOPE_EXIT,
        format: Optional[str] = None,  # noqa: A002
        mime_type: Optional[str] = None,
        refs: Optional[Dict[str, Any]] = None,
    ) -> RenderArtifact:
        """Register a raw data artifact (bytes, str, or MIME dict)."""
        if isinstance(data, bytes):
            kind = ArtifactKind.DATA_BYTES
        elif isinstance(data, str):
            kind = ArtifactKind.DATA_STR
        elif isinstance(data, dict):
            kind = ArtifactKind.DATA_MIME
        else:
            raise TypeError(f"Unsupported data type for register_data: {type(data).__name__}")
        extra_refs = dict(refs) if refs else {}
        if mime_type:
            extra_refs["mime_type"] = mime_type
        return self.register(
            kind,
            obj=data,
            scope_id=scope_id,
            owner=owner,
            refs=extra_refs,
            policy=policy,
            format=format,
        )

    # ------------------------------------------------------------------
    # USER_OUTPUT: artifacts that belong to the caller
    # ------------------------------------------------------------------

    def register_output_data(
        self,
        data: Union[bytes, str, Dict[str, Any]],
        *,
        scope_id: Optional[str] = None,
        owner: Optional[str] = None,
        format: Optional[str] = None,  # noqa: A002
        mime_type: Optional[str] = None,
        refs: Optional[Dict[str, Any]] = None,
    ) -> RenderArtifact:
        """Register a final data payload that is returned to the user.

        Unlike ``register_data``, the returned artifact has category
        ``USER_OUTPUT`` and will **not** be released by a bare
        ``release_all()`` or ``release_scope()`` call — only by
        explicitly passing ``include_user_output=True``.

        Use this for:
        - Final PNG/SVG/HTML bytes returned from ``renderer(obj)``
        - Notebook MIME bundles from ``components()`` or display hooks
        - Any payload whose ownership is transferred to the caller
        """
        if isinstance(data, (bytes, bytearray, memoryview)):
            kind = ArtifactKind.DATA_OUTPUT
        elif isinstance(data, str):
            kind = ArtifactKind.DATA_OUTPUT
        elif isinstance(data, dict):
            kind = ArtifactKind.MIME_OUTPUT
        else:
            raise TypeError(f"Unsupported data type for register_output_data: {type(data).__name__}")
        extra_refs = dict(refs) if refs else {}
        if mime_type:
            extra_refs["mime_type"] = mime_type
        return self.register(
            kind,
            obj=data,
            scope_id=scope_id,
            owner=owner,
            refs=extra_refs,
            policy=CleanupPolicy.MANUAL,
            format=format,
        )

    def register_output_file(
        self,
        path: str,
        *,
        scope_id: Optional[str] = None,
        owner: Optional[str] = None,
        format: Optional[str] = None,  # noqa: A002
        refs: Optional[Dict[str, Any]] = None,
    ) -> RenderArtifact:
        """Register a user-visible output file (e.g. from ``save()``).

        The resulting artifact has category ``USER_OUTPUT`` with
        policy ``MANUAL`` so ``release_all()`` will **not** delete
        the file.  The file is still tracked for debugging purposes,
        and callers may explicitly release it with
        ``artifact.release()`` or ``release_all(include_user_output=True)``.
        """
        extra_refs = dict(refs) if refs else {}
        extra_refs["output_path"] = path
        return self.register(
            ArtifactKind.FILE_OUTPUT,
            obj=None,
            scope_id=scope_id,
            owner=owner,
            path=path,
            refs=extra_refs,
            policy=CleanupPolicy.MANUAL,
            format=format,
        )

    def register_output_mime(
        self,
        bundle: Dict[str, Any],
        *,
        scope_id: Optional[str] = None,
        owner: Optional[str] = None,
        refs: Optional[Dict[str, Any]] = None,
    ) -> RenderArtifact:
        """Convenience wrapper for registering a notebook MIME bundle
        as a USER_OUTPUT artifact."""
        return self.register_output_data(
            bundle,
            scope_id=scope_id,
            owner=owner,
            format="mimebundle",
            refs=refs,
        )

    # ------------------------------------------------------------------
    # EXTERNAL_OBJECT: backend objects we hold a temporary reference to
    # ------------------------------------------------------------------

    def register_external_object(
        self,
        kind: Union[str, ArtifactKind],
        obj: Any,
        *,
        source: str = "renderer",
        scope_id: Optional[str] = None,
        owner: Optional[str] = None,
        format: Optional[str] = None,  # noqa: A002
        refs: Optional[Dict[str, Any]] = None,
        policy: Union[str, CleanupPolicy] = CleanupPolicy.RENDER_CYCLE,
    ) -> RenderArtifact:
        """Register a backend object (Bokeh/MPL/Plotly/Panel) that we
        hold a temporary reference to.

        Parameters
        ----------
        kind : ArtifactKind
            Must be in the EXTERNAL_OBJECT category.
        obj : Any
            The backend object to register.
        source : str, default "renderer"
            Who owns / created the object:
            - ``"renderer"`` (default): created by the renderer, we own
              the lifecycle and may tear it down on release.
            - ``"manager"``: created by the artifact manager itself.
            - ``"user"``: belongs to user code — release will **only**
              drop the tracking reference, never modify the object.
        refs : dict, optional
            Additional metadata; ``source`` is automatically added.

        Raises
        ------
        TypeError
            If ``kind`` is not in the EXTERNAL_OBJECT category.
        """
        kind = ArtifactKind(kind) if isinstance(kind, str) else kind
        if kind.category != ArtifactCategory.EXTERNAL_OBJECT:
            raise TypeError(
                f"register_external_object requires an EXTERNAL_OBJECT kind, "
                f"got {kind.value} (category {kind.category.value})"
            )
        if source not in {"renderer", "manager", "user"}:
            raise ValueError(f"source must be 'renderer', 'manager', or 'user', got {source!r}")
        extra_refs = dict(refs) if refs else {}
        extra_refs["source"] = source
        return self.register(
            kind,
            obj=obj,
            scope_id=scope_id,
            owner=owner,
            refs=extra_refs,
            policy=policy,
            format=format,
        )

    # ------------------------------------------------------------------
    # Plot registry (replaces Renderer._plots)
    # ------------------------------------------------------------------

    def register_plot(self, plot_id: str, plot: Any, *, scope_id: Optional[str] = None) -> RenderArtifact:
        """Register a plot object by id (replaces ``Renderer._plots`` dict)."""
        return self.register(
            ArtifactKind.PLOT_REGISTRY,
            obj=plot,
            scope_id=scope_id,
            refs={"plot_id": plot_id},
            policy=CleanupPolicy.MANUAL,
        )

    def get_plot(self, plot_id: str) -> Optional[Any]:
        for art in self._artifacts.values():
            if (
                art.kind == ArtifactKind.PLOT_REGISTRY
                and art.refs.get("plot_id") == plot_id
                and not art.released
            ):
                return art.obj
        return None

    def unregister_plot(self, plot_id: str) -> bool:
        for art in list(self._artifacts.values()):
            if (
                art.kind == ArtifactKind.PLOT_REGISTRY
                and art.refs.get("plot_id") == plot_id
            ):
                art.release()
                del self._artifacts[art.id]
                try:
                    self._by_scope[art.scope_id].discard(art.id)
                except KeyError:
                    pass
                return True
        return False

    # ------------------------------------------------------------------
    # Generic cache (LRU)
    # ------------------------------------------------------------------

    def cache_put(
        self,
        key: Any,
        value: Any,
        *,
        scope_id: Optional[str] = None,
        owner: Optional[str] = None,
        policy: Union[str, CleanupPolicy] = CleanupPolicy.RENDER_CYCLE,
        refs: Optional[Dict[str, Any]] = None,
        format: Optional[str] = None,  # noqa: A002
    ) -> RenderArtifact:
        """Insert ``value`` into the LRU cache under ``key``.

        If the key already exists, the previous entry is released and
        replaced.  When the cache exceeds ``cache_max`` entries, the
        least-recently-used entry is evicted.
        """
        if key in self._cache:
            prev_id = self._cache.pop(key)
            prev_art = self._artifacts.get(prev_id)
            if prev_art is not None:
                prev_art.release()
            del self._artifacts[prev_id]
            try:
                self._by_scope[prev_art.scope_id].discard(prev_id)
            except KeyError:
                pass

        artifact = self.register(
            ArtifactKind.CACHE_ENTRY,
            obj=value,
            scope_id=scope_id,
            owner=owner,
            refs=dict(refs, cache_key=repr(key)) if refs else {"cache_key": repr(key)},
            policy=policy,
            format=format,
        )
        self._cache[key] = artifact.id
        self._cache.move_to_end(key)

        while len(self._cache) > self.cache_max:
            _, evict_id = self._cache.popitem(last=False)
            evict_art = self._artifacts.pop(evict_id, None)
            if evict_art is not None:
                try:
                    self._by_scope[evict_art.scope_id].discard(evict_id)
                except KeyError:
                    pass
                evict_art.release()

        return artifact

    def cache_get(self, key: Any, default: Any = None) -> Any:
        """Look up ``key`` in the LRU cache.  Returns ``default`` on miss."""
        if key not in self._cache:
            return default
        self._cache.move_to_end(key)
        art_id = self._cache[key]
        art = self._artifacts.get(art_id)
        if art is None or art.released:
            self._cache.pop(key, None)
            self._artifacts.pop(art_id, None)
            return default
        return art.obj

    def cache_has(self, key: Any) -> bool:
        return key in self._cache and not self._artifacts[self._cache[key]].released

    def cache_pop(self, key: Any, default: Any = None) -> Any:
        """Remove and return the value for ``key`` from the LRU cache.

        If the key is not present, ``default`` is returned and no
        exception is raised.  The corresponding artifact is released
        and removed from tracking.
        """
        if key not in self._cache:
            return default
        art_id = self._cache.pop(key)
        art = self._artifacts.pop(art_id, None)
        value = default
        if art is not None:
            if not art.released:
                value = art.obj
                art.release()
            try:
                self._by_scope[art.scope_id].discard(art_id)
            except KeyError:
                pass
        return value

    def cache_delete(self, key: Any) -> bool:
        """Delete the cache entry for ``key``.

        Returns ``True`` if an entry existed and was removed,
        ``False`` if no entry existed.
        """
        return self.cache_pop(key, _SENTINEL) is not _SENTINEL

    def cache_clear(self) -> int:
        """Clear all LRU cache entries.  Returns number of entries removed."""
        count = 0
        for key in list(self._cache.keys()):
            art_id = self._cache.pop(key)
            art = self._artifacts.pop(art_id, None)
            if art is not None:
                try:
                    self._by_scope[art.scope_id].discard(art_id)
                except KeyError:
                    pass
                art.release()
                count += 1
        return count

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def list_artifacts(
        self,
        *,
        scope_id: Optional[str] = None,
        kind: Optional[Union[str, ArtifactKind]] = None,
        owner: Optional[str] = None,
        released: Optional[bool] = None,
        policy: Optional[Union[str, CleanupPolicy]] = None,
        format: Optional[str] = None,  # noqa: A002
        categories: Optional[Iterable[Union[str, ArtifactCategory]]] = None,
    ) -> List[RenderArtifact]:
        """Return a list of artifacts matching the given filters."""
        if kind is not None:
            kind = ArtifactKind(kind) if isinstance(kind, str) else kind
        if policy is not None:
            policy = CleanupPolicy(policy) if isinstance(policy, str) else policy
        allowed_categories: Optional[Set[ArtifactCategory]] = None
        if categories is not None:
            allowed_categories = {
                ArtifactCategory(c) if isinstance(c, str) else c for c in categories
            }
        results: List[RenderArtifact] = []
        for art in self._artifacts.values():
            if scope_id is not None and art.scope_id != scope_id:
                continue
            if kind is not None and art.kind != kind:
                continue
            if owner is not None and art.owner != owner:
                continue
            if released is not None and art.released != released:
                continue
            if policy is not None and art.policy != policy:
                continue
            if format is not None and art.format != format:
                continue
            if allowed_categories is not None and art.category not in allowed_categories:
                continue
            results.append(art)
        return results

    def get_artifact(self, artifact_id: str) -> Optional[RenderArtifact]:
        return self._artifacts.get(artifact_id)

    @property
    def total_artifacts(self) -> int:
        return len(self._artifacts)

    @property
    def unreleased_count(self) -> int:
        return sum(1 for a in self._artifacts.values() if not a.released)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def release_scope(
        self,
        scope_id: str,
        *,
        policy: Optional[Union[str, CleanupPolicy]] = None,
        include_user_output: bool = False,
        categories: Optional[Iterable[Union[str, ArtifactCategory]]] = None,
    ) -> int:
        """Release artifacts in ``scope_id``.

        Parameters
        ----------
        scope_id : str
            The scope whose artifacts should be released.
        policy : CleanupPolicy, optional
            If given, only artifacts matching the policy are released.
        include_user_output : bool, default False
            If ``False`` (the default), artifacts with category
            ``USER_OUTPUT`` are **never** released by this call, even
            if they match ``policy``.  Pass ``True`` to opt in to
            releasing user output as well.
        categories : iterable of ArtifactCategory, optional
            If given, only artifacts in these categories are released.
            When both ``categories`` and ``include_user_output`` are
            specified, both must allow a category for it to be
            released.

        Returns
        -------
        int
            Number of artifacts actually released in this call.
        """
        if policy is not None:
            policy = CleanupPolicy(policy) if isinstance(policy, str) else policy
        allowed_categories: Optional[Set[ArtifactCategory]] = None
        if categories is not None:
            allowed_categories = {
                ArtifactCategory(c) if isinstance(c, str) else c for c in categories
            }
        ids = self._by_scope.get(scope_id, set()).copy()
        count = 0
        for aid in ids:
            art = self._artifacts.get(aid)
            if art is None:
                continue
            if policy is not None and art.policy != policy:
                continue
            if not include_user_output and art.category == ArtifactCategory.USER_OUTPUT:
                continue
            if allowed_categories is not None and art.category not in allowed_categories:
                continue
            if art.release():
                count += 1
        return count

    def release_all(
        self,
        *,
        policy: Optional[Union[str, CleanupPolicy]] = None,
        include_user_output: bool = False,
        categories: Optional[Iterable[Union[str, ArtifactCategory]]] = None,
    ) -> int:
        """Release all tracked artifacts, respecting ownership boundaries.

        Parameters
        ----------
        policy : CleanupPolicy, optional
            Only release artifacts matching this policy.
        include_user_output : bool, default False
            ``USER_OUTPUT`` artifacts (files written by ``save()``,
            notebook MIME bundles returned to the user) are **never**
            released unless this flag is explicitly set to ``True``.
            This prevents accidental deletion of user files.
        categories : iterable of ArtifactCategory, optional
            If given, only release artifacts whose top-level ownership
            category is in this set.  ``USER_OUTPUT`` additionally
            requires ``include_user_output=True``.

        Returns
        -------
        int
            Number of artifacts actually released.
        """
        if policy is not None:
            policy = CleanupPolicy(policy) if isinstance(policy, str) else policy
        allowed_categories: Optional[Set[ArtifactCategory]] = None
        if categories is not None:
            allowed_categories = {
                ArtifactCategory(c) if isinstance(c, str) else c for c in categories
            }
        count = 0
        for art in list(self._artifacts.values()):
            if policy is not None and art.policy != policy:
                continue
            if art.category == ArtifactCategory.USER_OUTPUT and not include_user_output:
                continue
            if allowed_categories is not None and art.category not in allowed_categories:
                continue
            if art.release():
                count += 1
        # Purge released artifacts from tracking dicts
        self._purge_released()
        return count

    def mark_render_cycle(self, scope_id: str) -> None:
        """Record that a render cycle using ``scope_id`` has completed.

        Evicts old RENDER_CYCLE-policy scopes beyond ``cycle_retention``.
        """
        self._cycle_history.append(scope_id)
        while len(self._cycle_history) > self.cycle_retention:
            old_scope = self._cycle_history.pop(0)
            self.release_scope(old_scope, policy=CleanupPolicy.RENDER_CYCLE)

    def gc_collect(self) -> int:
        """Force garbage-collection style sweep and purge released entries."""
        gc.collect()
        return self._purge_released()

    # ------------------------------------------------------------------
    # Debug / introspection
    # ------------------------------------------------------------------

    def debug_summary(self) -> str:
        """Return a human-readable summary of currently tracked artifacts."""
        lines: List[str] = []
        lines.append(f"RenderArtifactManager summary")
        lines.append(f"  Total registered: {self.total_artifacts}")
        lines.append(f"  Unreleased:       {self.unreleased_count}")
        lines.append(f"  Active scopes:    {self._active_scopes}")
        lines.append(f"  Cache size:       {len(self._cache)}/{self.cache_max}")

        by_kind: Dict[str, int] = {}
        by_scope: Dict[str, int] = {}
        by_policy: Dict[str, int] = {}
        total_size = 0
        for art in self._artifacts.values():
            if art.released:
                continue
            by_kind[art.kind.value] = by_kind.get(art.kind.value, 0) + 1
            by_scope[art.scope_id] = by_scope.get(art.scope_id, 0) + 1
            by_policy[art.policy.value] = by_policy.get(art.policy.value, 0) + 1
            if art.size_bytes:
                total_size += art.size_bytes

        lines.append(f"  Est. memory:      {_fmt_size(total_size)}")
        lines.append("  By kind:")
        for k, v in sorted(by_kind.items()):
            lines.append(f"    {k}: {v}")
        lines.append("  By scope:")
        for k, v in sorted(by_scope.items()):
            lines.append(f"    {k}: {v}")
        lines.append("  By policy:")
        for k, v in sorted(by_policy.items()):
            lines.append(f"    {k}: {v}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_size(obj: Any, path: Optional[str], kind: ArtifactKind) -> Optional[int]:
        try:
            if isinstance(obj, (bytes, bytearray, memoryview)):
                return len(obj)
            if isinstance(obj, str):
                return len(obj.encode("utf-8"))
            if isinstance(obj, dict):
                total = 0
                for v in obj.values():
                    if isinstance(v, (bytes, bytearray, memoryview)):
                        total += len(v)
                    elif isinstance(v, str):
                        total += len(v.encode("utf-8"))
                return total or None
        except Exception:  # noqa: BLE001
            return None
        if path and os.path.exists(path):
            try:
                return os.path.getsize(path)
            except Exception:  # noqa: BLE001
                return None
        return None

    def _purge_released(self) -> int:
        purged = 0
        dead_ids = [aid for aid, art in self._artifacts.items() if art.released]
        for aid in dead_ids:
            art = self._artifacts.pop(aid, None)
            if art is not None:
                try:
                    self._by_scope[art.scope_id].discard(aid)
                    if not self._by_scope[art.scope_id]:
                        del self._by_scope[art.scope_id]
                except KeyError:
                    pass
                purged += 1
        # Clean cache too
        dead_keys = [k for k, aid in self._cache.items() if aid in dead_ids]
        for k in dead_keys:
            self._cache.pop(k, None)
        return purged

    def _atexit_cleanup(self) -> None:
        try:
            for art in list(self._artifacts.values()):
                if art.policy == CleanupPolicy.INTERPRETER_EXIT and not art.released:
                    try:
                        art.release()
                    except Exception:  # noqa: BLE001
                        pass
            for art in list(self._artifacts.values()):
                if (
                    art.kind in (ArtifactKind.FILE_TEMP, ArtifactKind.DIR_TEMP)
                    and not art.released
                ):
                    try:
                        art.release()
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Formatting helper
# ---------------------------------------------------------------------------


def _fmt_size(num: Optional[int]) -> str:
    if not num:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0  # type: ignore[assignment]
    return f"{num:.1f} PB"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

artifact_manager = RenderArtifactManager()


__all__ = [
    "ArtifactCategory",
    "ArtifactKind",
    "ArtifactScope",
    "CleanupPolicy",
    "RenderArtifact",
    "RenderArtifactManager",
    "artifact_manager",
]
