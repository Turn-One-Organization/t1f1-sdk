"""utils.delta_time: distance-aligned lap comparison."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from t1f1.utils import delta_time

T0 = datetime(2024, 8, 31, 13, 0, tzinfo=timezone.utc)


def _lap(distances: list[float], elapsed_seconds: list[float]) -> pl.DataFrame:
    timestamps = [T0 + timedelta(seconds=s) for s in elapsed_seconds]
    return pl.DataFrame({"timestamp": timestamps, "distance": distances}).with_columns(
        pl.col("timestamp").cast(pl.Datetime("us", "UTC")),
        pl.col("distance").cast(pl.Float32),
    )


def test_delta_time_identical_laps_gives_zero_delta():
    ref = _lap([0.0, 100.0, 200.0, 300.0], [0.0, 1.0, 2.0, 3.0])
    comp = _lap([0.0, 100.0, 200.0, 300.0], [0.0, 1.0, 2.0, 3.0])
    out = delta_time(ref, comp)
    assert out["delta_seconds"].to_list() == pytest.approx([0.0, 0.0, 0.0, 0.0], abs=1e-3)


def test_delta_time_slower_comparison_is_positive():
    ref = _lap([0.0, 100.0, 200.0, 300.0], [0.0, 1.0, 2.0, 3.0])
    # Comparison takes 1.5x as long to reach the same distances -> always behind.
    comp = _lap([0.0, 100.0, 200.0, 300.0], [0.0, 1.5, 3.0, 4.5])
    out = delta_time(ref, comp)
    assert out["delta_seconds"].to_list() == pytest.approx([0.0, 0.5, 1.0, 1.5], abs=1e-3)
    assert out["distance"].to_list() == pytest.approx([0.0, 100.0, 200.0, 300.0])


def test_delta_time_empty_input_returns_empty_schema():
    empty = pl.DataFrame(schema={"timestamp": pl.Datetime("us", "UTC"), "distance": pl.Float32})
    out = delta_time(empty, empty)
    assert out.is_empty()
    assert set(out.columns) == {"distance", "delta_seconds"}
