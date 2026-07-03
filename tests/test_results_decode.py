"""Session results/classification building + Q1/Q2/Q3 segmentation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import polars as pl

from t1f1.ingestion.results import build_results, segment_qualifying_laps
from t1f1.ingestion.stream import TIMESTAMP_KEY
from t1f1.schemas import RESULTS_SCHEMA

DRIVERS = {"1": {"tla": "VER", "team": "Red Bull"}, "4": {"tla": "NOR", "team": "McLaren"}}


def _record(ts: str, lines: dict[str, Any]) -> dict[str, Any]:
    return {TIMESTAMP_KEY: ts, "Lines": lines}


def test_build_results_basic_classification():
    timing = [
        _record("00:01:05.000", {"1": {"Position": "1"}}),
        _record("00:01:06.000", {"4": {"Position": "2"}}),
    ]
    timing_app = [_record("00:00:00.000", {"1": {"GridPos": "1"}, "4": {"GridPos": "3"}})]

    results = build_results(timing, timing_app, drivers=DRIVERS)

    assert results.schema == RESULTS_SCHEMA
    assert results["driver"].to_list() == ["VER", "NOR"]
    assert results["position"].to_list() == [1, 2]
    assert results["grid_position"].to_list() == [1, 3]
    assert results["status"].to_list() == ["Finished", "Finished"]


def test_build_results_flags_retired_status():
    timing = [_record("00:01:05.000", {"1": {"Position": "1", "Retired": True}})]
    results = build_results(timing, [], drivers=DRIVERS)
    assert results["status"].to_list() == ["Retired"]


def test_build_results_empty_input_returns_empty_schema():
    results = build_results([], [], drivers=DRIVERS)
    assert results.is_empty()
    assert results.schema == RESULTS_SCHEMA


def test_segment_qualifying_laps_splits_by_session_status():
    laps = pl.DataFrame(
        {
            "driver_number": ["1", "1", "1"],
            "lap_time_ms": [80_000, 79_000, 78_000],
            "lap_start_time": [
                datetime(2024, 8, 31, 13, 5, tzinfo=timezone.utc),
                datetime(2024, 8, 31, 13, 20, tzinfo=timezone.utc),
                datetime(2024, 8, 31, 13, 35, tzinfo=timezone.utc),
            ],
        }
    ).with_columns(
        pl.col("lap_time_ms").cast(pl.Duration("ms")).alias("lap_time"),
        pl.col("lap_start_time").cast(pl.Datetime("us", "UTC")),
    )

    session_status = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 8, 31, 13, 0, tzinfo=timezone.utc),
                datetime(2024, 8, 31, 13, 15, tzinfo=timezone.utc),
                datetime(2024, 8, 31, 13, 30, tzinfo=timezone.utc),
            ],
            "status": ["Started", "Started", "Started"],
        }
    ).with_columns(pl.col("timestamp").cast(pl.Datetime("us", "UTC")))

    segments = segment_qualifying_laps(laps, session_status)

    assert segments["1"]["q1"] == timedelta(seconds=80)
    assert segments["1"]["q2"] == timedelta(seconds=79)
    assert segments["1"]["q3"] == timedelta(seconds=78)


def test_segment_qualifying_laps_empty_status_returns_empty():
    laps = pl.DataFrame(schema={"driver_number": pl.Utf8, "lap_time": pl.Duration("ms")})
    session_status = pl.DataFrame(schema={"timestamp": pl.Datetime("us", "UTC"), "status": pl.Utf8})
    assert segment_qualifying_laps(laps, session_status) == {}
