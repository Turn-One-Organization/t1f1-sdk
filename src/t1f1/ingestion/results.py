"""Session results / classification from ``TimingData`` + ``TimingAppData``.

The raw feed carries live position/grid/retirement state but not free-text status
strings or championship points (those need Ergast — Module 4). For Qualifying,
Q1/Q2/Q3 best times are inferred by segmenting laps at ``SessionStatus``
Started->Finished transitions, since the feed doesn't label knockout segments itself.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from t1f1.ingestion.timing import _deep_merge, _int_or_none
from t1f1.schemas import RESULTS_SCHEMA, empty_results


def _final_driver_state(timing_records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Fold every TimingData delta in order to get each driver's final known state."""
    state: dict[str, dict[str, Any]] = {}
    for record in timing_records:
        lines = record.get("Lines")
        if not isinstance(lines, dict):
            continue
        for number, delta in lines.items():
            if not isinstance(delta, dict):
                continue
            _deep_merge(state.setdefault(number, {}), delta)
    return state


def _grid_positions(app_records: list[dict[str, Any]]) -> dict[str, int | None]:
    grid: dict[str, int | None] = {}
    for record in app_records:
        lines = record.get("Lines")
        if not isinstance(lines, dict):
            continue
        for number, delta in lines.items():
            if not isinstance(delta, dict):
                continue
            pos = delta.get("GridPos")
            if pos is not None:
                grid[number] = _int_or_none(pos)
    return grid


def _status_for(state: dict[str, Any]) -> str:
    if state.get("Retired"):
        return "Retired"
    if state.get("Stopped"):
        return "Stopped"
    return "Finished"


def segment_qualifying_laps(
    laps: pl.DataFrame, session_status: pl.DataFrame
) -> dict[str, dict[str, int | None]]:
    """Infer Q1/Q2/Q3 best times per driver from Started->Finished status segments.

    Returns ``driver_number -> {"q1": ms, "q2": ms, "q3": ms}``. If fewer than three
    Started segments are found (or timestamps are unavailable), later segments are
    left null rather than guessed.
    """
    if (
        laps.is_empty()
        or session_status.is_empty()
        or laps["lap_start_time"].null_count() == laps.height
    ):
        return {}

    starts = (
        session_status.filter(pl.col("status") == "Started")
        .filter(pl.col("timestamp").is_not_null())
        .sort("timestamp")["timestamp"]
        .to_list()
    )
    if not starts:
        return {}
    boundaries = starts + [None]  # None = open-ended for the final segment

    result: dict[str, dict[str, int | None]] = {}
    for seg_index, label in enumerate(("q1", "q2", "q3")):
        if seg_index >= len(starts):
            break
        start = boundaries[seg_index]
        end = boundaries[seg_index + 1]
        segment = laps.filter(pl.col("lap_start_time") >= start)
        if end is not None:
            segment = segment.filter(pl.col("lap_start_time") < end)
        if segment.is_empty():
            continue
        best = segment.group_by("driver_number").agg(pl.col("lap_time").min().alias(label))
        for row in best.iter_rows(named=True):
            result.setdefault(row["driver_number"], {})[label] = row[label]
    return result


def build_results(
    timing_records: list[dict[str, Any]],
    timing_app_records: list[dict[str, Any]],
    *,
    drivers: dict[str, dict[str, str]],
    qualifying_segments: dict[str, dict[str, int | None]] | None = None,
) -> pl.DataFrame:
    """Build a session results/classification frame from final TimingData state.

    ``qualifying_segments`` (see :func:`segment_qualifying_laps`) fills q1/q2/q3 for
    Qualifying/Sprint Qualifying; left null for Race/Practice sessions.
    """
    state = _final_driver_state(timing_records)
    grid = _grid_positions(timing_app_records)
    qualifying_segments = qualifying_segments or {}

    rows: list[dict[str, Any]] = []
    for number, driver_state in state.items():
        info = drivers.get(number, {})
        position = _int_or_none(driver_state.get("Position") or driver_state.get("Line"))
        segments = qualifying_segments.get(number, {})
        rows.append(
            {
                "driver": info.get("tla", number),
                "driver_number": number,
                "team": info.get("team"),
                "position": position,
                "classified_position": str(position) if position is not None else None,
                "grid_position": grid.get(number),
                "q1": segments.get("q1"),
                "q2": segments.get("q2"),
                "q3": segments.get("q3"),
                "time": None,
                "status": _status_for(driver_state),
                "points": None,
            }
        )
    if not rows:
        return empty_results()
    return pl.DataFrame(rows, schema=RESULTS_SCHEMA).sort("position")
