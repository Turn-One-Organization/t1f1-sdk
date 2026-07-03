"""analysis.py: free-tier local analysis compute (pure functions)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from t1f1.analysis import (
    COMPARE_SCHEMA,
    compare,
    driver_pace,
    qualifying_results,
    speed_distribution,
    speed_trap_top_speeds,
    teams_pace,
    track_dominance,
    tyre_stints,
)
from t1f1.frames.telemetry import add_relative_distance
from t1f1.schemas import LAP_SCHEMA, RESULTS_SCHEMA, empty_laps, empty_results, empty_telemetry

T0 = datetime(2024, 8, 31, 13, 0, tzinfo=timezone.utc)


def _lap_row(**overrides):
    row = {
        "lap_number": 1,
        "driver": "VER",
        "driver_number": "1",
        "team": "Red Bull Racing",
        "lap_time": timedelta(seconds=80),
        "lap_start_time": T0,
        "sector1_time": None,
        "sector2_time": None,
        "sector3_time": None,
        "speed_i1": None,
        "speed_i2": None,
        "speed_fl": None,
        "speed_st": 340.0,
        "is_personal_best": None,
        "compound": "SOFT",
        "tyre_life": 1,
        "fresh_tyre": True,
        "stint": 1,
        "pit_out_time": None,
        "pit_in_time": None,
        "position": 1,
        "track_status": "1",
        "deleted": False,
        "deleted_reason": None,
        "is_accurate": None,
    }
    row.update(overrides)
    return row


def _laps(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).cast(LAP_SCHEMA)


def _results_row(**overrides):
    row = {
        "driver": "VER",
        "driver_number": "1",
        "team": "Red Bull Racing",
        "position": 1,
        "classified_position": "1",
        "grid_position": 1,
        "q1": timedelta(seconds=81),
        "q2": timedelta(seconds=80),
        "q3": timedelta(seconds=79),
        "time": None,
        "status": "Finished",
        "points": None,
    }
    row.update(overrides)
    return row


def _results(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).cast(RESULTS_SCHEMA)


def _tel(distances, speeds, *, throttles=None, brakes=None, driver="VER", step_seconds=1.0):
    n = len(distances)
    throttles = throttles or [100.0] * n
    brakes = brakes or [0.0] * n
    timestamps = [T0 + timedelta(seconds=i * step_seconds) for i in range(n)]
    data = {
        "timestamp": timestamps,
        "driver": [driver] * n,
        "driver_number": ["1"] * n,
        "speed_kmh": [float(s) for s in speeds],
        "rpm": [11000] * n,
        "gear": [7] * n,
        "throttle": throttles,
        "brake": brakes,
        "drs": [0] * n,
        "distance": [float(d) for d in distances],
        "x": [0.0] * n,
        "y": [0.0] * n,
        "z": [0.0] * n,
    }
    return pl.DataFrame(data, schema=empty_telemetry().schema)


def test_speed_trap_top_speeds_picks_max_per_driver():
    laps = _laps(
        [
            _lap_row(driver="VER", lap_number=1, speed_st=330.0),
            _lap_row(driver="VER", lap_number=2, speed_st=345.0),
            _lap_row(driver="NOR", lap_number=1, speed_st=338.0),
        ]
    )
    result = speed_trap_top_speeds(laps)
    assert result["driver"].to_list() == ["VER", "NOR"]
    assert result["top_speed_kmh"].to_list() == pytest.approx([345.0, 338.0])
    assert result.filter(pl.col("driver") == "VER")["lap_number"].to_list() == [2]


def test_speed_trap_top_speeds_empty_input():
    result = speed_trap_top_speeds(empty_laps())
    assert result.is_empty()


def test_driver_pace_filters_quicklaps_and_box_laps():
    laps = _laps(
        [
            _lap_row(driver="VER", lap_number=1, lap_time=timedelta(seconds=80)),
            _lap_row(driver="VER", lap_number=2, lap_time=timedelta(seconds=81)),
            _lap_row(driver="VER", lap_number=3, lap_time=timedelta(seconds=82), pit_out_time=T0),
            _lap_row(driver="NOR", lap_number=1, lap_time=timedelta(seconds=200)),
        ]
    )
    result = driver_pace(laps)
    assert result["driver"].to_list() == ["VER"]
    row = result.row(0, named=True)
    assert row["laps"] == 2
    assert row["min"] == timedelta(seconds=80)


def test_teams_pace_groups_by_team():
    laps = _laps(
        [
            _lap_row(driver="VER", team="Red Bull Racing", lap_time=timedelta(seconds=80)),
            _lap_row(driver="PER", team="Red Bull Racing", lap_time=timedelta(seconds=81)),
        ]
    )
    result = teams_pace(laps)
    assert result["team"].to_list() == ["Red Bull Racing"]
    assert result.row(0, named=True)["laps"] == 2


def test_tyre_stints_groups_by_stint():
    laps = _laps(
        [
            _lap_row(driver="VER", lap_number=1, stint=1, compound="SOFT"),
            _lap_row(driver="VER", lap_number=2, stint=1, compound="SOFT"),
            _lap_row(driver="VER", lap_number=3, stint=2, compound="HARD"),
        ]
    )
    result = tyre_stints(laps)
    assert result.height == 2
    row0 = result.row(0, named=True)
    assert row0 == {
        "driver": "VER",
        "team": "Red Bull Racing",
        "stint": 1,
        "compound": "SOFT",
        "start_lap": 1,
        "end_lap": 2,
        "lap_count": 2,
    }


def test_qualifying_results_adds_gap_to_pole():
    results = _results(
        [
            _results_row(driver="VER", position=1, q3=timedelta(seconds=79)),
            _results_row(driver="NOR", position=2, q3=timedelta(seconds=79, microseconds=500_000)),
        ]
    )
    out = qualifying_results(results)
    assert out["gap_to_pole"].to_list() == [timedelta(0), timedelta(microseconds=500_000)]


def test_qualifying_results_empty_input():
    out = qualifying_results(empty_results())
    assert out.is_empty()
    assert "gap_to_pole" in out.columns


def test_speed_distribution_bins_speeds():
    tel = _tel([0, 1, 2, 3, 4], [100.0, 150.0, 200.0, 250.0, 300.0])
    out = speed_distribution(tel, bins=5)
    assert out.height == 5
    assert out["count"].sum() == 5


def test_speed_distribution_empty_input():
    out = speed_distribution(empty_telemetry())
    assert out.is_empty()


def test_compare_aligns_by_distance_and_computes_delta():
    tel1 = _tel([0.0, 100.0, 200.0], [300.0, 310.0, 320.0], step_seconds=1.0)
    tel2 = _tel([0.0, 100.0, 200.0], [290.0, 300.0, 310.0], step_seconds=1.5)
    result = compare(tel1, tel2)
    assert result.schema == COMPARE_SCHEMA
    assert result.height == 3
    assert result["driver1_speed_kmh"].to_list() == pytest.approx([300.0, 310.0, 320.0])
    assert result["driver2_speed_kmh"].to_list() == pytest.approx([290.0, 300.0, 310.0])
    assert result["delta_seconds"].to_list() == pytest.approx([0.0, 0.5, 1.0], abs=1e-3)


def test_compare_empty_input():
    result = compare(empty_telemetry(), empty_telemetry())
    assert result.is_empty()
    assert result.schema == COMPARE_SCHEMA


def test_track_dominance_picks_faster_driver_per_minisector():
    tel1 = add_relative_distance(_tel([0.0, 50.0, 100.0], [300.0, 200.0, 100.0]))
    tel2 = add_relative_distance(_tel([0.0, 50.0, 100.0], [250.0, 250.0, 250.0], driver="NOR"))
    result = track_dominance(tel1, tel2, driver1="VER", driver2="NOR", n_minisectors=2).sort(
        "minisector"
    )
    assert result["minisector"].to_list() == [0, 1]
    assert result["faster"].to_list() == ["VER", "NOR"]


def test_track_dominance_requires_relative_distance():
    tel1 = _tel([0.0, 50.0], [300.0, 200.0])
    tel2 = _tel([0.0, 50.0], [250.0, 250.0], driver="NOR")
    result = track_dominance(tel1, tel2, driver1="VER", driver2="NOR")
    assert result.is_empty()
