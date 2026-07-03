"""frames/telemetry.py: vectorized, composable transforms."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from t1f1.frames.telemetry import (
    add_differential_distance,
    add_distance,
    add_relative_distance,
    add_track_status,
    compute_driver_ahead,
    fill_missing,
    merge_channels,
    resample_channels,
    slice_by_mask,
    slice_by_time,
)
from t1f1.schemas import empty_telemetry

T0 = datetime(2024, 8, 31, 13, 0, 0, tzinfo=timezone.utc)


def _tel(n: int, *, speed=300.0, driver="VER", driver_number="1", step_seconds=1.0) -> pl.DataFrame:
    timestamps = [T0 + timedelta(seconds=i * step_seconds) for i in range(n)]
    data = {
        "timestamp": timestamps,
        "driver": [driver] * n,
        "driver_number": [driver_number] * n,
        "speed_kmh": [float(speed)] * n,
        "rpm": [11000] * n,
        "gear": [7] * n,
        "throttle": [100.0] * n,
        "brake": [0.0] * n,
        "drs": [0] * n,
        "distance": [0.0] * n,
        "x": [float(i) for i in range(n)],
        "y": [float(i) for i in range(n)],
        "z": [0.0] * n,
    }
    return pl.DataFrame(data, schema=empty_telemetry().schema)


def test_add_distance_integrates_speed_over_time():
    # 360 km/h = 100 m/s.
    out = add_distance(_tel(3, speed=360.0, step_seconds=1.0))
    assert out["distance"].to_list() == pytest.approx([0.0, 100.0, 200.0], abs=0.5)


def test_add_differential_distance():
    out = add_differential_distance(add_distance(_tel(3, speed=360.0)))
    assert out["differential_distance"].to_list() == pytest.approx([0.0, 100.0, 100.0], abs=0.5)


def test_add_relative_distance_normalises_0_to_1():
    out = add_relative_distance(add_distance(_tel(3, speed=360.0)))
    values = out["relative_distance"].to_list()
    assert values[0] == pytest.approx(0.0)
    assert values[-1] == pytest.approx(1.0)


def test_add_track_status_backward_join():
    df = _tel(3)
    track_status = pl.DataFrame(
        {
            "timestamp": [T0 - timedelta(seconds=10), T0 + timedelta(seconds=1, milliseconds=500)],
            "status": ["1", "2"],
        }
    ).with_columns(pl.col("timestamp").cast(pl.Datetime("us", "UTC")))
    out = add_track_status(df, track_status)
    assert out["track_status"].to_list() == ["1", "1", "2"]


def test_merge_channels_nearest_join():
    df = _tel(2)
    weather = pl.DataFrame({"timestamp": [T0], "air_temp": [25.0]}).with_columns(
        pl.col("timestamp").cast(pl.Datetime("us", "UTC"))
    )
    out = merge_channels(df, weather)
    assert out["air_temp"].to_list() == [25.0, 25.0]


def test_slice_by_time_is_inclusive_both_ends():
    out = slice_by_time(_tel(5), T0 + timedelta(seconds=1), T0 + timedelta(seconds=3))
    assert out.height == 3


def test_slice_by_mask():
    df = _tel(4)
    out = slice_by_mask(df, df["speed_kmh"] > 0)
    assert out.height == 4


def test_resample_channels_preserves_columns():
    n = 10
    df = _tel(n, step_seconds=0.1).with_columns(
        pl.Series("speed_kmh", [float(i) for i in range(n)])
    )
    out = resample_channels(df, every="500ms")
    assert out.height >= 1
    assert set(out.columns) == set(df.columns)


def test_fill_missing_forward_and_back_fills():
    df = _tel(3).with_columns(pl.Series("throttle", [None, 50.0, None]).cast(pl.Float32))
    out = fill_missing(df)
    assert out["throttle"].to_list() == [50.0, 50.0, 50.0]


def test_compute_driver_ahead_finds_nearest_positive_gap():
    target = add_distance(_tel(3, speed=360.0, driver="VER", driver_number="1"))
    ahead_close = add_distance(_tel(3, speed=360.0, driver="NOR", driver_number="4"))
    ahead_close = ahead_close.with_columns((pl.col("distance") + 50.0).alias("distance"))
    ahead_far = add_distance(_tel(3, speed=360.0, driver="PIA", driver_number="81"))
    ahead_far = ahead_far.with_columns((pl.col("distance") + 500.0).alias("distance"))

    result = compute_driver_ahead(target, {"NOR": ahead_close, "PIA": ahead_far})
    assert result["driver_ahead"].to_list() == ["NOR", "NOR", "NOR"]
    assert result["distance_to_driver_ahead"].to_list() == pytest.approx([50.0, 50.0, 50.0])


def test_compute_driver_ahead_no_one_ahead_returns_null():
    target = add_distance(_tel(2, speed=360.0))
    behind = add_distance(_tel(2, speed=360.0, driver="NOR", driver_number="4"))
    behind = behind.with_columns((pl.col("distance") - 100.0).alias("distance"))
    result = compute_driver_ahead(target, {"NOR": behind})
    assert result["driver_ahead"].to_list() == [None, None]


def test_compute_driver_ahead_no_others_returns_null_columns():
    target = add_distance(_tel(2, speed=360.0))
    result = compute_driver_ahead(target, {})
    assert result["driver_ahead"].to_list() == [None, None]
    assert result["distance_to_driver_ahead"].to_list() == [None, None]


def test_empty_frames_are_noop_passthrough():
    empty = empty_telemetry()
    assert add_distance(empty).is_empty()
    assert add_relative_distance(empty).is_empty()
    assert slice_by_time(empty, T0, T0).is_empty()
    assert resample_channels(empty).is_empty()
    assert fill_missing(empty).is_empty()
