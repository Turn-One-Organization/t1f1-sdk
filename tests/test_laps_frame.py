"""LapsFrame: chainable pick_* filters over a laps frame."""

from __future__ import annotations

from datetime import datetime, timezone

import polars as pl

from t1f1.frames.laps import LapsFrame
from t1f1.schemas import empty_laps

BASE = empty_laps().schema


def _laps(**overrides: list) -> LapsFrame:
    n = len(next(iter(overrides.values())))
    data = {
        "lap_number": list(range(1, n + 1)),
        "driver": ["VER"] * n,
        "driver_number": ["1"] * n,
        "team": ["Red Bull"] * n,
        "lap_time": [70_000 + i * 1000 for i in range(n)],
        "lap_start_time": [datetime(2024, 8, 31, 13, i, tzinfo=timezone.utc) for i in range(n)],
        "sector1_time": [None] * n,
        "sector2_time": [None] * n,
        "sector3_time": [None] * n,
        "speed_i1": [None] * n,
        "speed_i2": [None] * n,
        "speed_fl": [None] * n,
        "speed_st": [None] * n,
        "is_personal_best": [None] * n,
        "compound": ["SOFT"] * n,
        "tyre_life": [1] * n,
        "fresh_tyre": [True] * n,
        "stint": [1] * n,
        "pit_out_time": [None] * n,
        "pit_in_time": [None] * n,
        "position": [1] * n,
        "track_status": ["1"] * n,
        "deleted": [False] * n,
        "deleted_reason": [None] * n,
        "is_accurate": [True] * n,
    }
    data.update(overrides)
    frame = pl.DataFrame(data).with_columns(pl.col("lap_time").cast(pl.Duration("ms")))
    return LapsFrame(frame.cast(BASE))


def test_pick_drivers_and_teams():
    frame = pl.DataFrame(
        {
            "driver": ["VER", "NOR"],
            "team": ["Red Bull", "McLaren"],
        }
    )
    laps = LapsFrame(frame)
    assert laps.pick_drivers("ver").to_polars()["driver"].to_list() == ["VER"]
    assert laps.pick_teams("mclaren").to_polars()["driver"].to_list() == ["NOR"]


def test_pick_compounds_and_laps():
    frame = pl.DataFrame({"compound": ["SOFT", "HARD"], "lap_number": [1, 2]})
    laps = LapsFrame(frame)
    assert laps.pick_compounds("hard").to_polars()["lap_number"].to_list() == [2]
    assert laps.pick_laps(1).to_polars()["lap_number"].to_list() == [1]
    assert laps.pick_laps([1, 2]).to_polars().height == 2


def test_pick_not_deleted_and_accurate():
    frame = pl.DataFrame(
        {"deleted": [False, True, None], "is_accurate": [True, True, None], "lap_number": [1, 2, 3]}
    )
    laps = LapsFrame(frame)
    assert laps.pick_not_deleted().to_polars()["lap_number"].to_list() == [1, 3]
    assert laps.pick_accurate().to_polars()["lap_number"].to_list() == [1, 2, 3]


def test_pick_wo_box_and_box_laps():
    frame = pl.DataFrame(
        {
            "pit_in_time": [None, datetime(2024, 8, 31, 13, 0, tzinfo=timezone.utc)],
            "pit_out_time": [None, None],
            "lap_number": [1, 2],
        }
    )
    laps = LapsFrame(frame)
    assert laps.pick_wo_box().to_polars()["lap_number"].to_list() == [1]
    assert laps.pick_box_laps().to_polars()["lap_number"].to_list() == [2]


def test_pick_quicklaps_and_fastest():
    laps = _laps(lap_time=[70_000, 74_900, 75_100, 80_000])
    fastest = laps.pick_fastest()
    assert len(fastest) == 1
    assert fastest.to_polars()["lap_number"].to_list() == [1]

    quick = laps.pick_quicklaps(threshold=1.07)
    # 70s * 1.07 = 74.9s -> laps 1 and 2 qualify, 3 (75.1s) and 4 (80s) don't.
    assert quick.to_polars()["lap_number"].to_list() == [1, 2]


def test_iterlaps_yields_named_rows():
    laps = _laps(lap_time=[70_000, 71_000])
    rows = list(laps.iterlaps())
    assert len(rows) == 2
    assert rows[0]["driver"] == "VER"


def test_split_qualifying_sessions_without_segment_column_returns_self():
    laps = _laps(lap_time=[70_000])
    assert laps.split_qualifying_sessions() == [laps]
