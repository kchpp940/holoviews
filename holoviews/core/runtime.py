"""
Runtime state management for HoloViews dynamic elements.

This module provides the DynamicMapContext class which encapsulates all
runtime state of a DynamicMap, separating it from the data container
responsibilities of the DynamicMap main class.

The Context manages:
- Stream parameters and posarg key mapping
- Callback execution logic
- Cache key management and LRU cache updates
- Current frame tracking (current_key, last_key)
- Event trigger reason and metadata

External components (streams, renderers, plotting utilities) should interact
with the runtime state through the Context interface rather than accessing
DynamicMap internals directly.
"""

from __future__ import annotations

import weakref
from typing import Any, Dict, List, Optional, Tuple

from . import util
from .options import StoreOptions, Store


class DynamicMapContext:
    """Independent runtime state context for DynamicMap.

    Manages the following runtime state, separated from the DynamicMap main class:
    - stream parameters (_posarg_keys, stream parameter list)
    - callback execution logic
    - cache key and cache state
    - current frame (current_key)
    - last key tracking
    - event trigger reason

    The DynamicMap main class retains only public API; runtime state is managed by this Context.
    """

    def __init__(self, dmap):
        self._dmap_ref = weakref.ref(dmap)
        self._current_key = None
        self._last_key = None
        self._posarg_keys = None
        self._event_reason = None
        self._event_metadata = {}

    @property
    def _dmap(self):
        dmap = self._dmap_ref()
        if dmap is None:
            raise ReferenceError("DynamicMapContext referencing a garbage-collected DynamicMap")
        return dmap

    @property
    def current_key(self):
        """Key of the frame currently being accessed (most recent __getitem__ key)."""
        return self._current_key

    @current_key.setter
    def current_key(self, value):
        self._current_key = value

    @property
    def last_key(self):
        """Key of the most recently computed and cached frame."""
        if len(self._dmap.data):
            return list(self._dmap.data.keys())[-1]
        return self._last_key

    @property
    def last_frame(self):
        """Most recently computed frame (Element/Overlay etc.)."""
        if len(self._dmap.data):
            return list(self._dmap.data.values())[-1]
        return None

    @property
    def event_reason(self):
        """Description of the most recent event trigger reason, used for debug."""
        return self._event_reason

    @property
    def event_metadata(self):
        """Additional metadata from the most recent event."""
        return dict(self._event_metadata)

    def set_event_reason(self, reason, **metadata):
        """Record the trigger reason and metadata for an event."""
        self._event_reason = reason
        self._event_metadata = dict(metadata)

    def clear_event_reason(self):
        """Clear the event trigger reason record."""
        self._event_reason = None
        self._event_metadata = {}

    def stream_parameters(self, no_duplicates=None):
        """Get list of parameter names from all streams."""
        if no_duplicates is None:
            no_duplicates = not self._dmap.positional_stream_args
        return util.stream_parameters(self._dmap.streams, no_duplicates=no_duplicates)

    def initialize_posarg_keys(self):
        """Initialize the mapping from callback parameters to kdims."""
        if self._dmap.positional_stream_args:
            self._posarg_keys = None
        else:
            self._posarg_keys = util.validate_dynamic_argspec(
                self._dmap.callback, self._dmap.kdims, self._dmap.streams
            )

    @property
    def posarg_keys(self):
        """Positional argument keys mapping callback params to kdims."""
        return self._posarg_keys

    def initial_key(self):
        """Construct initial key from lower bounds or values of each dimension."""
        dmap = self._dmap
        key = []
        undefined = []
        stream_params = set(self.stream_parameters())
        for kdim in dmap.kdims:
            if str(kdim) in stream_params:
                key.append(None)
            elif kdim.default is not None:
                key.append(kdim.default)
            elif kdim.values:
                if all(util.isnumeric(v) for v in kdim.values):
                    key.append(sorted(kdim.values)[0])
                else:
                    key.append(kdim.values[0])
            elif kdim.range[0] is not None:
                key.append(kdim.range[0])
            else:
                undefined.append(kdim)
        if undefined:
            msg = (
                "Dimension(s) {undefined_dims} do not specify range or values needed "
                "to generate initial key"
            )
            undefined_dims = ", ".join(f"{str(dim)!r}" for dim in undefined)
            raise KeyError(msg.format(undefined_dims=undefined_dims))
        return tuple(key)

    def validate_key(self, key):
        """Validate that key values are within range/soft_range bounds of their dimensions."""
        dmap = self._dmap
        if key == () and len(dmap.kdims) == 0:
            return ()
        key = util.wrap_tuple(key)
        assert len(key) == len(dmap.kdims)
        for ind, val in enumerate(key):
            kdim = dmap.kdims[ind]
            low, high = util.max_range([kdim.range, kdim.soft_range])
            if util.is_number(low) and util.isfinite(low):
                if val < low:
                    raise KeyError(f"Key value {val} below lower bound {low}")
            if util.is_number(high) and util.isfinite(high):
                if val > high:
                    raise KeyError(f"Key value {val} above upper bound {high}")

    def _style(self, retval):
        """Apply custom option tree to callback return value."""
        from ..util import opts

        dmap = self._dmap
        if dmap.id not in Store.custom_options():
            return retval
        spec = StoreOptions.tree_to_dict(Store.custom_options()[dmap.id])
        return opts.apply_groups(retval, options=spec)

    def execute_callback(self, *args):
        """Execute the callback with appropriate args and kwargs (including stream values)."""
        dmap = self._dmap
        self.validate_key(args)

        kdims = [kdim.name for kdim in dmap.kdims]
        kwarg_items = [s.contents.items() for s in dmap.streams]
        hash_items = tuple(tuple(sorted(s.hashkey.items())) for s in dmap.streams) + args
        flattened = [(k, v) for kws in kwarg_items for (k, v) in kws if k not in kdims]

        if dmap.positional_stream_args:
            kwargs = {}
            args = args + tuple([s.contents for s in dmap.streams])
        elif self._posarg_keys:
            kwargs = dict(flattened, **dict(zip(self._posarg_keys, args, strict=False)))
            args = ()
        else:
            kwargs = dict(flattened)
        if not isinstance(dmap.callback, _get_generator_class()):
            kwargs["_memoization_hash_"] = hash_items

        # 延迟导入避免循环引用
        from .spaces import dynamicmap_memoization
        with dynamicmap_memoization(dmap.callback, dmap.streams):
            retval = dmap.callback(*args, **kwargs)
        return self._style(retval)

    def cache_value(self, key, val):
        """Request to cache a (key, val) pair (LRU)."""
        dmap = self._dmap
        cache_size = (
            1
            if util.dimensionless_contents(
                dmap.streams, dmap.kdims, no_duplicates=not dmap.positional_stream_args
            )
            else dmap.cache_size
        )
        if len(dmap) >= cache_size:
            first_key = next(k for k in dmap.data)
            dmap.data.pop(first_key)
        dmap[key] = val
        self._last_key = key

    def handle_event(self, **kwargs):
        """Find corresponding streams from kwargs, update parameters and trigger events.

        Returns the list of streams actually triggered.
        """
        from ..streams import Stream

        dmap = self._dmap
        if dmap.callback.noargs and dmap.streams == []:
            dmap.param.warning(
                "No streams declared. To update a DynamicMaps using "
                "generators (or callables without arguments) use streams=[Next()]"
            )
            return []
        if dmap.streams == []:
            dmap.param.warning("No streams on DynamicMap, calling event will have no effect")
            return []

        stream_params = set(self.stream_parameters())
        invalid = [k for k in kwargs.keys() if k not in stream_params]
        if invalid:
            msg = "Key(s) {invalid} do not correspond to stream parameters"
            raise KeyError(msg.format(invalid=", ".join(f"{i!r}" for i in invalid)))

        self.set_event_reason("manual_event", triggered_params=list(kwargs.keys()))

        triggered = []
        for stream in dmap.streams:
            contents = stream.contents
            applicable_kws = {k: v for k, v in kwargs.items() if k in set(contents.keys())}
            if not applicable_kws and contents:
                continue
            triggered.append(stream)
            rkwargs = util.rename_stream_kwargs(stream, applicable_kws, reverse=True)
            stream.update(**rkwargs)

        Stream.trigger(triggered)
        return triggered

    def get_frame(self, key_map, cached=False):
        """Get a frame by key_map (dimension name -> value).

        This is the stable interface for renderers and plotting utilities
        to retrieve frames from a DynamicMap through its Context.

        Parameters
        ----------
        key_map : dict
            Dictionary mapping dimension names to key values
        cached : bool
            Whether to allow looking up key in cache without computing

        Returns
        -------
        The frame corresponding to the supplied key mapping.
        """
        dmap = self._dmap
        if (
            dmap.kdims
            and len(dmap.kdims) == 1
            and dmap.kdims[0] == "Frame"
            and not dmap.unbounded
        ):
            key = key_map.get("Frame", 0)
            if key in dmap.data:
                return dmap.data[key]
            if isinstance(key, int) and len(dmap.data) > key:
                return list(dmap.data.values())[key]

        key = tuple(key_map.get(d.name, None) for d in dmap.kdims)
        if cached and key in dmap.data:
            return dmap.data[key]
        return dmap[key]

    def resolve_posarg_key(self, kwargs):
        """Resolve a key from kwargs using posarg_keys mapping.

        Used by operation utilities to construct keys from stream kwargs.

        Parameters
        ----------
        kwargs : dict
            Keyword arguments containing values for posarg keys

        Returns
        -------
        tuple or None
            The resolved key tuple, or None if posarg_keys is not set
            or if any required posarg key is missing from kwargs
        """
        if self._posarg_keys:
            try:
                return tuple(kwargs[k] for k in self._posarg_keys)
            except KeyError:
                return None
        return None

    def initialize(self):
        """Initialize the DynamicMap by computing the initial frame.

        This is the stable interface for plotting utilities to initialize
        a DynamicMap before rendering.
        """
        dmap = self._dmap
        if dmap.unbounded:
            return
        if not len(dmap):
            dmap[self.initial_key()]


class Generator:
    """Placeholder for Generator type to avoid circular imports."""
    pass


def _get_generator_class():
    """Lazy import of Generator to avoid circular import with spaces.py."""
    from .spaces import Generator
    return Generator

