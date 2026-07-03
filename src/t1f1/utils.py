"""Cross-lap analysis helpers that don't belong to a single frame type."""

from __future__ import annotations

import numpy as np
import polars as pl

_DELTA_SCHEMA = {"distance": pl.Float32, "delta_seconds": pl.Float32}


def delta_time(reference: pl.DataFrame, comparison: pl.DataFrame) -> pl.DataFrame:
    """Time delta between two laps' telemetry, aligned by distance.

    Returns one row per ``reference`` sample: ``distance`` (reference's distance
    grid) and ``delta_seconds`` (comparison's elapsed time at that distance minus
    reference's elapsed time — **positive means comparison is behind/slower** at
    that point on track). Both frames need ``timestamp`` and ``distance`` columns;
    call :func:`t1f1.frames.telemetry.add_distance` first if slicing changed the
    sample grid (e.g. after ``slice_by_time``).
    """
    if reference.is_empty() or comparison.is_empty():
        return pl.DataFrame(schema=_DELTA_SCHEMA)

    ref = reference.sort("distance")
    comp = comparison.sort("distance")

    ref_elapsed = (
        ref["timestamp"] - ref["timestamp"].min()
    ).dt.total_milliseconds().to_numpy() / 1000.0
    comp_elapsed = (
        comp["timestamp"] - comp["timestamp"].min()
    ).dt.total_milliseconds().to_numpy() / 1000.0

    ref_distance = ref["distance"].to_numpy()
    comp_distance = comp["distance"].to_numpy()

    # Interpolate comparison's elapsed time onto reference's distance grid.
    comp_elapsed_interp = np.interp(ref_distance, comp_distance, comp_elapsed)
    delta = comp_elapsed_interp - ref_elapsed

    return pl.DataFrame(
        {
            "distance": ref_distance.astype(np.float32),
            "delta_seconds": delta.astype(np.float32),
        }
    )
