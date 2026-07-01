"""Canonical polars schemas for the SDK's data products.

Owning explicit, typed schemas (with documented units) is a deliberate advantage over
fastf1's implicit ``object``-dtyped pandas frames. Later modules extend this with
``LAP_SCHEMA``, ``RESULTS_SCHEMA``, ``WEATHER_SCHEMA``, etc.
"""

from __future__ import annotations

import polars as pl

#: A single per-sample telemetry row for one driver.
#:
#: Units: ``speed_kmh`` km/h, ``rpm`` rev/min, ``gear`` 0-8 (0 = neutral),
#: ``throttle`` 0-100 %, ``brake`` 0-100 % (or 0/1 on some sessions), ``drs`` raw
#: DRS indicator, ``distance`` metres (cumulative from first sample),
#: ``x``/``y``/``z`` position in 1/10 m (F1 raw units).
TELEMETRY_SCHEMA: dict[str, pl.DataType] = {
    "timestamp": pl.Datetime(time_unit="us", time_zone="UTC"),
    "driver": pl.Utf8,
    "driver_number": pl.Utf8,
    "speed_kmh": pl.Float32,
    "rpm": pl.Int32,
    "gear": pl.Int8,
    "throttle": pl.Float32,
    "brake": pl.Float32,
    "drs": pl.Int8,
    "distance": pl.Float32,
    "x": pl.Float32,
    "y": pl.Float32,
    "z": pl.Float32,
}

TELEMETRY_COLUMNS: list[str] = list(TELEMETRY_SCHEMA)


def empty_telemetry() -> pl.DataFrame:
    """Return an empty telemetry frame with the canonical schema."""
    return pl.DataFrame(schema=TELEMETRY_SCHEMA)
