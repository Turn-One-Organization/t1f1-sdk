"""Lap reconstruction from ``TimingData`` + ``TimingAppData``.

``TimingData`` lines are *partial deltas* merged onto per-driver running state, not
full snapshots — nested keys like ``Sectors``/``Speeds`` arrive one sub-key at a time.
A lap is complete once a delta carries ``LastLapTime.Value``; at that point we emit a
row from the accumulated state and reset the per-lap accumulator (sector/speed
fields) while keeping cross-lap identity/position state.
"""

from __future__ import annotations

import copy
from typing import Any

import polars as pl

from t1f1.ingestion.session_clock import SessionClock
from t1f1.ingestion.stream import TIMESTAMP_KEY
from t1f1.schemas import LAP_SCHEMA, empty_laps


def _deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> None:
    """Recursively merge ``src`` into ``dst`` in place.

    A shallow ``dict.update`` would drop sibling sub-keys (e.g. sector 1's value)
    when a delta only carries an update to sector 2. Dict values are deep-copied
    rather than aliased: ``src`` is a reference into the *raw, cached* feed records,
    and later merging further updates into ``dst[key]`` must never mutate that
    shared original (this corrupted ``RawF1Source._timing_records`` in place and made
    repeated ``laps()`` calls on the same session return different results).
    """
    for key, value in src.items():
        if isinstance(value, dict):
            if isinstance(dst.get(key), dict):
                _deep_merge(dst[key], value)
            else:
                dst[key] = copy.deepcopy(value)
        else:
            dst[key] = value


def _parse_duration_ms(value: str | None) -> int | None:
    """Parse an F1 lap/sector time string (``"1:21.045"`` or ``"28.887"``) to ms."""
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    sign = 1
    if text.startswith("-"):
        sign = -1
        text = text[1:]
    parts = text.split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = parts
            total_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        elif len(parts) == 2:
            minutes, seconds = parts
            total_seconds = int(minutes) * 60 + float(seconds)
        else:
            total_seconds = float(parts[0])
    except ValueError:
        return None
    return sign * round(total_seconds * 1000)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_speed(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _value_of(container: Any, key: str) -> str | None:
    if not isinstance(container, dict):
        return None
    entry = container.get(key)
    if isinstance(entry, dict):
        return entry.get("Value")
    return None


def _build_stint_ranges(app_records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Reconstruct each driver's tyre-stint lap ranges from ``TimingAppData``."""
    stint_state: dict[str, dict[str, dict[str, Any]]] = {}
    for record in app_records:
        lines = record.get("Lines")
        if not isinstance(lines, dict):
            continue
        for number, delta in lines.items():
            if not isinstance(delta, dict):
                continue
            stints_delta = delta.get("Stints")
            # The feed sends the initial stint announcement as a *list* (index is
            # positional) but subsequent pit-stop updates as a *dict* keyed by index
            # string — confirmed against a live 2024 Monza race feed.
            if isinstance(stints_delta, dict):
                items = stints_delta.items()
            elif isinstance(stints_delta, list):
                items = enumerate(stints_delta)
            else:
                continue
            driver_stints = stint_state.setdefault(number, {})
            for idx, stint_delta in items:
                if not isinstance(stint_delta, dict):
                    continue
                _deep_merge(driver_stints.setdefault(str(idx), {}), stint_delta)

    ranges: dict[str, list[dict[str, Any]]] = {}
    for number, stints in stint_state.items():
        cursor = 0
        driver_ranges: list[dict[str, Any]] = []
        for stint_number, idx in enumerate(
            sorted(stints, key=lambda k: _int_or_none(k) or 0), start=1
        ):
            stint = stints[idx]
            total_laps = _int_or_none(stint.get("TotalLaps")) or 1
            start_tyre_life = _int_or_none(stint.get("StartLaps")) or 0
            start_lap = cursor + 1
            end_lap = cursor + total_laps
            driver_ranges.append(
                {
                    "stint": stint_number,
                    "compound": stint.get("Compound"),
                    "start_lap": start_lap,
                    "end_lap": end_lap,
                    "start_tyre_life": start_tyre_life,
                    "fresh_tyre": str(stint.get("New", "")).lower() == "true",
                }
            )
            cursor = end_lap
        ranges[number] = driver_ranges
    return ranges


def _stint_for_lap(driver_ranges: list[dict[str, Any]], lap_number: int) -> dict[str, Any] | None:
    for stint_range in driver_ranges:
        if stint_range["start_lap"] <= lap_number <= stint_range["end_lap"]:
            return stint_range
    return driver_ranges[-1] if driver_ranges else None


def decode_laps(
    timing_records: list[dict[str, Any]],
    timing_app_records: list[dict[str, Any]],
    *,
    drivers: dict[str, dict[str, str]],
    clock: SessionClock | None = None,
) -> pl.DataFrame:
    """Reconstruct completed laps for all drivers from raw ``TimingData`` records.

    ``drivers`` maps racing number -> ``{"tla": ..., "team": ...}`` (from
    ``DriverList.json``). ``clock`` anchors line timestamps to absolute UTC; without
    it ``lap_start_time``/``pit_out_time``/``pit_in_time`` are null.
    """
    stint_ranges = _build_stint_ranges(timing_app_records)
    state: dict[str, dict[str, Any]] = {}
    lap_counter: dict[str, int] = {}
    lap_start: dict[str, Any] = {}
    pit_out: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []

    # A driver's very first lap has no prior lap-completion timestamp to start from;
    # anchor it to the feed's earliest record instead of leaving it null, so e.g. Q1
    # segmentation (which keys off lap_start_time) doesn't silently drop first laps.
    session_start_ts = None
    if clock is not None and timing_records:
        first_ts = timing_records[0].get(TIMESTAMP_KEY)
        if first_ts:
            session_start_ts = clock.to_utc(first_ts)

    for record in timing_records:
        lines = record.get("Lines")
        if not isinstance(lines, dict):
            continue
        timestamp = clock.to_utc(record.get(TIMESTAMP_KEY)) if clock else None

        for number, delta in lines.items():
            if not isinstance(delta, dict):
                continue
            driver_state = state.setdefault(number, {})
            _deep_merge(driver_state, delta)

            if delta.get("PitOut"):
                pit_out[number] = timestamp
            if delta.get("InPit"):
                driver_state["_pit_in_ts"] = timestamp

            last_lap = delta.get("LastLapTime")
            last_lap_value = last_lap.get("Value") if isinstance(last_lap, dict) else None
            if not last_lap_value:
                continue

            lap_number = lap_counter.get(number, 0) + 1
            lap_counter[number] = lap_number

            info = drivers.get(number, {})
            driver_ranges = stint_ranges.get(number, [])
            stint = _stint_for_lap(driver_ranges, lap_number)
            tyre_life = None
            if stint is not None:
                tyre_life = stint["start_tyre_life"] + (lap_number - stint["start_lap"] + 1)

            rows.append(
                {
                    "lap_number": lap_number,
                    "driver": info.get("tla", number),
                    "driver_number": number,
                    "team": info.get("team"),
                    "lap_time": _parse_duration_ms(last_lap_value),
                    "lap_start_time": lap_start.get(number, session_start_ts),
                    "sector1_time": _parse_duration_ms(_value_of(driver_state.get("Sectors"), "0")),
                    "sector2_time": _parse_duration_ms(_value_of(driver_state.get("Sectors"), "1")),
                    "sector3_time": _parse_duration_ms(_value_of(driver_state.get("Sectors"), "2")),
                    "speed_i1": _as_speed(_value_of(driver_state.get("Speeds"), "I1")),
                    "speed_i2": _as_speed(_value_of(driver_state.get("Speeds"), "I2")),
                    "speed_fl": _as_speed(_value_of(driver_state.get("Speeds"), "FL")),
                    "speed_st": _as_speed(_value_of(driver_state.get("Speeds"), "ST")),
                    "is_personal_best": (
                        bool(last_lap.get("PersonalFastest"))
                        if isinstance(last_lap, dict)
                        else None
                    ),
                    "compound": stint["compound"] if stint else None,
                    "tyre_life": tyre_life,
                    "fresh_tyre": stint["fresh_tyre"] if stint else None,
                    "stint": stint["stint"] if stint else None,
                    "pit_out_time": pit_out.get(number),
                    "pit_in_time": driver_state.pop("_pit_in_ts", None),
                    "position": _int_or_none(
                        driver_state.get("Position") or driver_state.get("Line")
                    ),
                    "track_status": None,
                    # Deletion isn't reliably signalled in the fields decoded so far;
                    # left False pending live-feed confirmation (see Module 2 plan).
                    "deleted": False,
                    "deleted_reason": None,
                    "is_accurate": None,
                }
            )

            lap_start[number] = timestamp
            pit_out[number] = None
            driver_state["Sectors"] = {}
            driver_state["Speeds"] = {}
            driver_state.pop("LastLapTime", None)

    if not rows:
        return empty_laps()
    return pl.DataFrame(rows, schema=LAP_SCHEMA).sort(["driver_number", "lap_number"])


def attach_track_status(laps: pl.DataFrame, track_status: pl.DataFrame) -> pl.DataFrame:
    """Stamp each lap's ``track_status`` via a nearest-before join on lap start time.

    ``join_asof`` requires non-null join keys, and a lap's ``lap_start_time`` is null
    for a driver's very first tracked lap (no prior timestamp exists yet) — those rows
    are carried through unmatched instead of being dropped or erroring the join.
    """
    columns = list(LAP_SCHEMA.keys())
    if laps.is_empty() or track_status.is_empty():
        return laps
    known = laps.filter(pl.col("lap_start_time").is_not_null())
    unknown = laps.filter(pl.col("lap_start_time").is_null())
    if known.is_empty():
        return laps

    left = known.drop("track_status").sort("lap_start_time")
    right = track_status.select(["timestamp", "status"]).sort("timestamp")
    joined = (
        left.join_asof(right, left_on="lap_start_time", right_on="timestamp", strategy="backward")
        .rename({"status": "track_status"})
        .drop("timestamp")
        .select(columns)
    )
    return pl.concat([joined, unknown.select(columns)], how="vertical").sort(
        ["driver_number", "lap_number"]
    )
