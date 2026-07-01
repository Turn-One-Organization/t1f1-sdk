"""Decode raw CarData/Position stream records into a typed polars telemetry frame.

The channel map is the canonical F1/fastf1 one. **NOTE:** one docs-exploration pass
claimed ``0=Speed / 2=RPM``; that is the swapped (wrong) reading. The mapping below
matches fastf1 and is asserted empirically in the test-suite against a recorded
payload — do not "correct" it without checking a real CarData sample.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from t1f1.schemas import TELEMETRY_COLUMNS, TELEMETRY_SCHEMA, empty_telemetry

#: CarData ``Channels`` index -> canonical column name (fastf1 mapping).
CAR_CHANNELS: dict[str, str] = {
    "0": "rpm",
    "2": "speed_kmh",
    "3": "gear",
    "4": "throttle",
    "5": "brake",
    "45": "drs",
}

_KMH_TO_MS = 1000.0 / 3600.0


def decode_car_data(records: list[dict[str, Any]], driver_number: str) -> list[dict[str, Any]]:
    """Flatten decoded CarData records into per-sample rows for one driver.

    Each record has an ``Entries`` list of samples; each sample has a ``Utc`` stamp
    and a ``Cars`` map keyed by driver number, each with a ``Channels`` dict.
    """
    driver_number = str(driver_number)
    rows: list[dict[str, Any]] = []
    for record in records:
        for sample in record.get("Entries", []):
            car = sample.get("Cars", {}).get(driver_number)
            if not car:
                continue
            channels = car.get("Channels", {})
            row: dict[str, Any] = {"timestamp": sample.get("Utc")}
            for channel_id, name in CAR_CHANNELS.items():
                row[name] = channels.get(channel_id)
            rows.append(row)
    return rows


def decode_position(records: list[dict[str, Any]], driver_number: str) -> list[dict[str, Any]]:
    """Flatten decoded Position records into per-sample X/Y/Z rows for one driver.

    Each record has a ``Position`` list; each item has a ``Timestamp`` and an
    ``Entries`` map keyed by driver number with ``X``/``Y``/``Z``/``Status``.
    """
    driver_number = str(driver_number)
    rows: list[dict[str, Any]] = []
    for record in records:
        for sample in record.get("Position", []):
            entry = sample.get("Entries", {}).get(driver_number)
            if not entry:
                continue
            rows.append(
                {
                    "timestamp": sample.get("Timestamp"),
                    "x": entry.get("X"),
                    "y": entry.get("Y"),
                    "z": entry.get("Z"),
                }
            )
    return rows


def _to_utc(expr: pl.Expr) -> pl.Expr:
    """Parse ISO-8601 UTC strings (F1 uses trailing ``Z`` and variable precision)."""
    return expr.str.to_datetime(time_zone="UTC", time_unit="us", strict=False)


def build_telemetry(
    car_rows: list[dict[str, Any]],
    pos_rows: list[dict[str, Any]],
    *,
    driver: str,
    driver_number: str,
) -> pl.DataFrame:
    """Merge CarData + Position rows into a schema-correct telemetry DataFrame.

    Position samples are aligned to car samples by nearest timestamp (as-of join),
    and ``distance`` is integrated from speed over time.
    """
    if not car_rows:
        return empty_telemetry()

    car = (
        pl.DataFrame(car_rows)
        .with_columns(_to_utc(pl.col("timestamp")).alias("timestamp"))
        .drop_nulls("timestamp")
        .sort("timestamp")
        .unique(subset="timestamp", keep="first", maintain_order=True)
    )

    if pos_rows:
        pos = (
            pl.DataFrame(pos_rows)
            .with_columns(_to_utc(pl.col("timestamp")).alias("timestamp"))
            .drop_nulls("timestamp")
            .sort("timestamp")
            .unique(subset="timestamp", keep="first", maintain_order=True)
        )
        car = car.join_asof(pos, on="timestamp", strategy="nearest")

    # Integrate distance = cumulative sum of speed (m/s) * dt (s).
    dt_seconds = pl.col("timestamp").diff().dt.total_nanoseconds().cast(pl.Float64) / 1e9
    speed_ms = pl.col("speed_kmh").cast(pl.Float64) * _KMH_TO_MS
    distance = (speed_ms * dt_seconds.fill_null(0.0)).cum_sum().alias("distance")

    frame = car.with_columns(
        pl.lit(driver).alias("driver"),
        pl.lit(str(driver_number)).alias("driver_number"),
        distance,
    )

    # Ensure every schema column exists, then cast to the canonical schema/order.
    for column in TELEMETRY_COLUMNS:
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None).alias(column))
    return frame.select(TELEMETRY_COLUMNS).cast(TELEMETRY_SCHEMA)  # type: ignore[arg-type]
