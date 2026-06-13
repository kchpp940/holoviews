"""Verify datashader operations are guarded on dynamic path.

Note: May not actually run datashader due to numba/numpy version issues,
but we can verify the class hierarchy and guard integration.
"""
import sys
import traceback

print("=" * 70)
print("TEST: Verify datashader operation guard integration")
print("=" * 70)

try:
    from holoviews.operation.datashader import (
        AggregationOperation,
        aggregate,
        rasterize,
        regrid,
        datashade,
        area_aggregate,
        spread_aggregate,
        spikes_aggregate,
        geom_aggregate,
        trimesh_rasterize,
        overlay_aggregate,
    )
    from holoviews.operation.guard import OperationGuard, GuardedOperationMixin
    from holoviews.operation.resample import GuardedResampleOperation2D

    print("\n✅ Successfully imported datashader operations")

    # Check MRO for key operations
    ops_to_check = [
        ("AggregationOperation", AggregationOperation),
        ("aggregate", aggregate),
        ("rasterize", rasterize),
        ("regrid", regrid),
        ("datashade", datashade),
        ("area_aggregate", area_aggregate),
        ("spread_aggregate", spread_aggregate),
        ("spikes_aggregate", spikes_aggregate),
        ("geom_aggregate", geom_aggregate),
        ("trimesh_rasterize", trimesh_rasterize),
        ("overlay_aggregate", overlay_aggregate),
    ]

    print("\n--- MRO Analysis ---")
    for name, op_cls in ops_to_check:
        mro_names = [c.__name__ for c in op_cls.__mro__]
        has_guard = any('Guard' in n or 'guard' in n for n in mro_names)
        has_operation_guard = OperationGuard in op_cls.__mro__
        has_guarded_mixin = GuardedOperationMixin in op_cls.__mro__
        has_guarded_2d = GuardedResampleOperation2D in op_cls.__mro__
        
        has_process_core = hasattr(op_cls, '_process_core')
        has_own_process = '_process' in op_cls.__dict__
        
        print(f"\n  {name}:")
        print(f"    MRO (first 6): {mro_names[:6]}")
        print(f"    Has OperationGuard: {has_operation_guard}")
        print(f"    Has GuardedResampleOperation2D: {has_guarded_2d}")
        print(f"    Has _process_core method: {has_process_core}")
        print(f"    Overrides _process in class: {has_own_process}")

    # Check which operations have _process_core (meaning they've been refactored)
    print("\n--- Operations with _process_core (guard-refactored) ---")
    for name, op_cls in ops_to_check:
        if hasattr(op_cls, '_process_core') and '_process_core' in op_cls.__dict__:
            print(f"  ✅ {name}")

    print("\n--- Operations that override _process directly (may bypass guard) ---")
    for name, op_cls in ops_to_check:
        if '_process' in op_cls.__dict__:
            print(f"  ⚠️  {name}")

except ImportError as e:
    print(f"\n❌ Cannot import datashader: {e}")
    print("This is expected due to numba/numpy version issues.")
    traceback.print_exc()

print("\n" + "=" * 70)
print("Summary")
print("=" * 70)
