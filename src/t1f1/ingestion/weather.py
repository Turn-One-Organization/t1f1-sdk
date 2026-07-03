"""Parser for ``WeatherData.jsonStream``.

Each line is a full snapshot (not an incremental delta), so decoding is a direct
field-by-field flatten + numeric cast — the raw feed carries everything as strings.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from t1f1.ingestion.session_clock import SessionClock
from t1f1.ingestion.stream import TIMESTAMP_KEY
from t1f1.schemas import WEATHER_SCHEMA


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return str(value).strip() not in ("0", "", "false", "False")


def decode_weather(
    records: list[dict[str, Any]], *, clock: SessionClock | None = None
) -> pl.DataFrame:
    """Flatten ``WeatherData.jsonStream`` records into a typed frame.

    ``clock`` anchors each line's session-clock prefix to absolute UTC; without it
    (or without a resolvable session date) ``timestamp`` is null.
    """
    rows = [
        {
            "timestamp": clock.to_utc(record.get(TIMESTAMP_KEY)) if clock else None,
            "air_temp": _as_float(record.get("AirTemp")),
            "track_temp": _as_float(record.get("TrackTemp")),
            "humidity": _as_float(record.get("Humidity")),
            "pressure": _as_float(record.get("Pressure")),
            "rainfall": _as_bool(record.get("Rainfall")),
            "wind_direction": _as_float(record.get("WindDirection")),
            "wind_speed": _as_float(record.get("WindSpeed")),
        }
        for record in records
    ]
    if not rows:
        return pl.DataFrame(schema=WEATHER_SCHEMA)
    return pl.DataFrame(rows, schema=WEATHER_SCHEMA)
