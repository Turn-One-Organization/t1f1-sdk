"""Lap reconstruction: deep-merge, stint mapping, lap emission on LastLapTime."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import polars as pl
import pytest

from t1f1.ingestion.session_clock import SessionClock
from t1f1.ingestion.stream import TIMESTAMP_KEY
from t1f1.ingestion.timing import _deep_merge, decode_laps
from t1f1.schemas import LAP_SCHEMA

DRIVERS = {"1": {"tla": "VER", "team": "Red Bull"}}


def _record(ts: str, lines: dict[str, Any]) -> dict[str, Any]:
    return {TIMESTAMP_KEY: ts, "Lines": lines}


def test_deep_merge_preserves_sibling_keys():
    dst = {"Sectors": {"0": {"Value": "28.887"}}}
    _deep_merge(dst, {"Sectors": {"1": {"Value": "24.500"}}})
    assert dst == {"Sectors": {"0": {"Value": "28.887"}, "1": {"Value": "24.500"}}}


def test_deep_merge_does_not_alias_or_mutate_the_source():
    # Regression: dst[key] = value used to alias src's nested dicts by reference, so
    # a later merge into dst silently mutated the *source* record too — this
    # corrupted RawF1Source._timing_records in place and made a second decode_laps()
    # call over the same cached records produce different (wrong) laps.
    src = {"Sectors": {"0": {"Value": "28.887"}}}
    dst: dict = {}
    _deep_merge(dst, src)
    dst["Sectors"]["0"]["Value"] = "999.999"
    assert src == {"Sectors": {"0": {"Value": "28.887"}}}


def test_decode_laps_is_idempotent_across_repeated_calls():
    # Regression: calling decode_laps twice over the *same* record list must give
    # identical results (it must never mutate its input).
    timing = [
        _record("00:00:05.000", {"1": {"Sectors": {"0": {"Value": "28.887"}}}}),
        _record("00:00:35.000", {"1": {"Sectors": {"1": {"Value": "24.500"}}}}),
        _record(
            "00:01:05.000",
            {
                "1": {
                    "Sectors": {"2": {"Value": "26.900"}},
                    "LastLapTime": {"Value": "1:20.287"},
                }
            },
        ),
        _record("00:01:40.000", {"1": {"Sectors": {"0": {"Value": "30.000"}}}}),
        _record(
            "00:02:45.000",
            {
                "1": {
                    "Sectors": {"1": {"Value": "25.000"}, "2": {"Value": "27.000"}},
                    "LastLapTime": {"Value": "1:22.000"},
                }
            },
        ),
    ]
    first = decode_laps(timing, [], drivers=DRIVERS)
    second = decode_laps(timing, [], drivers=DRIVERS)
    assert first.equals(second)
    assert second["lap_time"].to_list() == first["lap_time"].to_list()


def test_decode_laps_does_not_choke_on_a_long_run_of_null_pit_columns():
    # Regression, found live against real 2024 Race sessions: pl.DataFrame(rows)
    # infers each column's dtype from a sample of the first ~100 rows (polars'
    # default infer_schema_length). pit_out_time is null for most laps (no pit stop)
    # — if it stays null past that sample window and only becomes a real datetime on
    # a later pit stop (routine on a 150+ lap race with a long first stint), the
    # already-inferred dtype couldn't hold it and construction raised a ComputeError.
    # Fixed by passing schema= directly to pl.DataFrame() instead of infer-then-cast.
    clock = SessionClock(datetime(2024, 8, 31, 13, 0, 0, tzinfo=timezone.utc))
    timing = []
    elapsed = 0
    for lap in range(1, 151):
        elapsed += 80
        ts = f"{elapsed // 3600:02d}:{(elapsed % 3600) // 60:02d}:{elapsed % 60:02d}.000"
        delta: dict[str, Any] = {"LastLapTime": {"Value": "1:20.000"}}
        if lap == 130:
            delta = {"PitOut": True, **delta}
        timing.append(_record(ts, {"1": delta}))

    laps = decode_laps(timing, [], drivers=DRIVERS, clock=clock)

    assert laps.height == 150
    assert laps["pit_out_time"].null_count() == 149


def test_decode_laps_emits_row_on_last_lap_time():
    timing = [
        _record("00:00:05.000", {"1": {"Sectors": {"0": {"Value": "28.887"}}}}),
        _record("00:00:35.000", {"1": {"Sectors": {"1": {"Value": "24.500"}}}}),
        _record(
            "00:01:05.000",
            {
                "1": {
                    "Sectors": {"2": {"Value": "26.900"}},
                    "Speeds": {"FL": {"Value": "320"}},
                    "Position": "1",
                    "LastLapTime": {"Value": "1:20.287", "PersonalFastest": True},
                }
            },
        ),
    ]
    laps = decode_laps(timing, [], drivers=DRIVERS)

    assert laps.schema == LAP_SCHEMA
    assert laps.height == 1
    row = laps.row(0, named=True)
    assert row["driver"] == "VER"
    assert row["team"] == "Red Bull"
    assert row["lap_number"] == 1
    assert row["lap_time"].total_seconds() == pytest.approx(80.287)
    assert row["sector1_time"].total_seconds() == pytest.approx(28.887)
    assert row["speed_fl"] == pytest.approx(320.0)
    assert row["position"] == 1
    assert row["is_personal_best"] is True


def test_decode_laps_resets_sectors_between_laps():
    timing = [
        _record(
            "00:01:05.000",
            {
                "1": {
                    "Sectors": {
                        "0": {"Value": "28.0"},
                        "1": {"Value": "24.0"},
                        "2": {"Value": "27.0"},
                    },
                    "LastLapTime": {"Value": "1:19.000"},
                }
            },
        ),
        _record("00:01:40.000", {"1": {"Sectors": {"0": {"Value": "30.0"}}}}),
        _record(
            "00:02:45.000",
            {
                "1": {
                    "Sectors": {"1": {"Value": "25.0"}, "2": {"Value": "27.0"}},
                    "LastLapTime": {"Value": "1:22.000"},
                }
            },
        ),
    ]
    laps = decode_laps(timing, [], drivers=DRIVERS)

    assert laps.height == 2
    lap2 = laps.filter(pl.col("lap_number") == 2).row(0, named=True)
    # lap 2's sector1 must be the reset value, not lap 1's leftover 28.0.
    assert lap2["sector1_time"].total_seconds() == pytest.approx(30.0)


SESSION_START = datetime(2024, 8, 31, 13, 0, 0, tzinfo=timezone.utc)


def test_initial_stint_announced_as_list_is_read_as_stint_zero():
    # Confirmed against a live 2024 Monza race feed: the *first* stint announcement
    # arrives as a list (index implied by position); later pit-stop updates arrive as
    # a dict keyed by index string. Both shapes must map to the same stint 0/1/...
    timing = [_record("00:01:05.000", {"1": {"LastLapTime": {"Value": "1:20.000"}}})]
    timing_app = [
        _record(
            "00:00:00.000",
            {
                "1": {
                    "Stints": [
                        {"Compound": "MEDIUM", "New": "true", "StartLaps": 0, "TotalLaps": 0}
                    ]
                }
            },
        ),
    ]
    laps = decode_laps(timing, timing_app, drivers=DRIVERS)
    assert laps["compound"].to_list() == ["MEDIUM"]


def test_stint_and_pit_merge():
    clock = SessionClock(SESSION_START)
    timing = [
        _record("00:01:05.000", {"1": {"LastLapTime": {"Value": "1:20.000"}}}),
        _record("00:01:10.000", {"1": {"InPit": True}}),
        _record("00:02:10.000", {"1": {"PitOut": True}}),
        _record("00:02:45.000", {"1": {"LastLapTime": {"Value": "1:22.000"}}}),
    ]
    timing_app = [
        _record(
            "00:00:00.000",
            {
                "1": {
                    "Stints": {
                        "0": {"Compound": "SOFT", "New": "true", "StartLaps": 0, "TotalLaps": 1}
                    }
                }
            },
        ),
        _record(
            "00:01:30.000",
            {
                "1": {
                    "Stints": {
                        "1": {"Compound": "HARD", "New": "true", "StartLaps": 0, "TotalLaps": 1}
                    }
                }
            },
        ),
    ]
    laps = decode_laps(timing, timing_app, drivers=DRIVERS, clock=clock).sort("lap_number")

    assert laps["compound"].to_list() == ["SOFT", "HARD"]
    assert laps["stint"].to_list() == [1, 2]
    lap2 = laps.row(1, named=True)
    assert lap2["pit_in_time"] is not None
    assert lap2["pit_out_time"] is not None


def test_clock_anchors_first_lap_to_session_start_and_later_laps_to_prior_completion():
    clock = SessionClock(SESSION_START)
    timing = [
        _record("00:00:10.000", {"1": {}}),  # earliest record -> session start anchor
        _record("00:01:05.000", {"1": {"LastLapTime": {"Value": "1:20.000"}}}),
        _record("00:02:30.000", {"1": {"LastLapTime": {"Value": "1:21.000"}}}),
    ]
    laps = decode_laps(timing, [], drivers=DRIVERS, clock=clock).sort("lap_number")

    lap1, lap2 = laps.row(0, named=True), laps.row(1, named=True)
    assert lap1["lap_start_time"] == SESSION_START + timedelta(seconds=10)
    # lap 2 starts when lap 1 finished, not at the session anchor.
    assert lap2["lap_start_time"] == SESSION_START + timedelta(seconds=65)


def test_without_clock_lap_start_time_is_null():
    timing = [_record("00:01:05.000", {"1": {"LastLapTime": {"Value": "1:20.000"}}})]
    laps = decode_laps(timing, [], drivers=DRIVERS)
    assert laps.row(0, named=True)["lap_start_time"] is None
