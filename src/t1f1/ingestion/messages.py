"""Parsers for the F1 feed's simple/near-flat streams.

Unlike ``TimingData`` (incremental per-driver deltas), ``TrackStatus``,
``SessionStatus``, ``RaceControlMessages``, and ``LapCount`` are effectively a full
snapshot per line, so no state-merging is needed — just flatten each record into a row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import polars as pl

from t1f1.ingestion.session_clock import SessionClock
from t1f1.ingestion.stream import TIMESTAMP_KEY
from t1f1.schemas import (
    RACE_CONTROL_SCHEMA,
    SESSION_STATUS_SCHEMA,
    TRACK_STATUS_SCHEMA,
)


def decode_track_status(
    records: list[dict[str, Any]], *, clock: SessionClock | None = None
) -> pl.DataFrame:
    """Flatten ``TrackStatus.jsonStream`` records into a typed frame."""
    rows = [
        {
            "timestamp": clock.to_utc(record.get(TIMESTAMP_KEY)) if clock else None,
            "status": record.get("Status"),
            "message": record.get("Message"),
        }
        for record in records
    ]
    if not rows:
        return pl.DataFrame(schema=TRACK_STATUS_SCHEMA)
    return pl.DataFrame(rows, schema=TRACK_STATUS_SCHEMA)


def decode_session_status(
    records: list[dict[str, Any]], *, clock: SessionClock | None = None
) -> pl.DataFrame:
    """Flatten ``SessionStatus.jsonStream`` records into a typed frame."""
    rows = [
        {
            "timestamp": clock.to_utc(record.get(TIMESTAMP_KEY)) if clock else None,
            "status": record.get("Status"),
        }
        for record in records
    ]
    if not rows:
        return pl.DataFrame(schema=SESSION_STATUS_SCHEMA)
    return pl.DataFrame(rows, schema=SESSION_STATUS_SCHEMA)


def _parse_embedded_utc(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def decode_race_control_messages(
    records: list[dict[str, Any]], *, clock: SessionClock | None = None
) -> pl.DataFrame:
    """Flatten ``RaceControlMessages.jsonStream`` records into a typed frame.

    ``Messages`` may be a dict keyed by index or a list, depending on feed version.
    Prefers an embedded absolute ``Utc`` per message; falls back to the line's
    session-clock prefix via ``clock``.
    """
    rows: list[dict[str, Any]] = []
    for record in records:
        messages = record.get("Messages") or []
        entries = messages.values() if isinstance(messages, dict) else messages
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            sector = entry.get("Sector")
            lap = entry.get("Lap")
            embedded_utc = entry.get("Utc")
            timestamp = _parse_embedded_utc(embedded_utc) if embedded_utc else None
            if timestamp is None and clock is not None:
                timestamp = clock.to_utc(record.get(TIMESTAMP_KEY))
            rows.append(
                {
                    "timestamp": timestamp,
                    "category": entry.get("Category"),
                    "message": entry.get("Message"),
                    "flag": entry.get("Flag"),
                    "scope": entry.get("Scope"),
                    "sector": int(sector) if sector is not None else None,
                    "lap": int(lap) if lap is not None else None,
                }
            )
    if not rows:
        return pl.DataFrame(schema=RACE_CONTROL_SCHEMA)
    return pl.DataFrame(rows, schema=RACE_CONTROL_SCHEMA)


def latest_total_laps(records: list[dict[str, Any]]) -> int | None:
    """Return the most recent ``TotalLaps`` seen in ``LapCount.jsonStream``, if any."""
    total: int | None = None
    for record in records:
        value = record.get("TotalLaps")
        if value is not None:
            total = int(value)
    return total
