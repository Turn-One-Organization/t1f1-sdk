"""Canonical polars schemas for the SDK's data products.

Owning explicit, typed schemas (with documented units) is a deliberate advantage over
fastf1's implicit ``object``-dtyped pandas frames.
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


#: One completed lap for one driver.
#:
#: Units: ``*_time``/``lap_time`` are durations (``pl.Duration("ms")``, not fastf1's
#: pandas ``Timedelta`` objects). ``speed_i1``/``speed_i2``/``speed_fl``/``speed_st``
#: are speed-trap readings in km/h. ``tyre_life`` is laps completed on the current set.
LAP_SCHEMA: dict[str, pl.DataType] = {
    "lap_number": pl.Int32,
    "driver": pl.Utf8,
    "driver_number": pl.Utf8,
    "team": pl.Utf8,
    "lap_time": pl.Duration("ms"),
    "lap_start_time": pl.Datetime(time_unit="us", time_zone="UTC"),
    "sector1_time": pl.Duration("ms"),
    "sector2_time": pl.Duration("ms"),
    "sector3_time": pl.Duration("ms"),
    "speed_i1": pl.Float32,
    "speed_i2": pl.Float32,
    "speed_fl": pl.Float32,
    "speed_st": pl.Float32,
    "is_personal_best": pl.Boolean,
    "compound": pl.Utf8,
    "tyre_life": pl.Int32,
    "fresh_tyre": pl.Boolean,
    "stint": pl.Int32,
    "pit_out_time": pl.Datetime(time_unit="us", time_zone="UTC"),
    "pit_in_time": pl.Datetime(time_unit="us", time_zone="UTC"),
    "position": pl.Int32,
    "track_status": pl.Utf8,
    "deleted": pl.Boolean,
    "deleted_reason": pl.Utf8,
    "is_accurate": pl.Boolean,
}

LAP_COLUMNS: list[str] = list(LAP_SCHEMA)


def empty_laps() -> pl.DataFrame:
    """Return an empty laps frame with the canonical schema."""
    return pl.DataFrame(schema=LAP_SCHEMA)


#: Final classification for one driver in one session.
#:
#: ``q1``/``q2``/``q3``/``time`` are durations. ``classified_position`` is a string
#: because non-finishers are classified as e.g. ``"R"``/``"D"``/``"NC"``, not a number.
RESULTS_SCHEMA: dict[str, pl.DataType] = {
    "driver": pl.Utf8,
    "driver_number": pl.Utf8,
    "team": pl.Utf8,
    "position": pl.Int32,
    "classified_position": pl.Utf8,
    "grid_position": pl.Int32,
    "q1": pl.Duration("ms"),
    "q2": pl.Duration("ms"),
    "q3": pl.Duration("ms"),
    "time": pl.Duration("ms"),
    "status": pl.Utf8,
    "points": pl.Float32,
}

RESULTS_COLUMNS: list[str] = list(RESULTS_SCHEMA)


def empty_results() -> pl.DataFrame:
    """Return an empty results frame with the canonical schema."""
    return pl.DataFrame(schema=RESULTS_SCHEMA)


#: One weather sample. Units: temps in °C, humidity/rainfall %, pressure mbar,
#: wind_direction degrees, wind_speed m/s.
#:
#: WeatherData carries no embedded absolute UTC field, only the feed's session-clock
#: line prefix (``HH:MM:SS.mmm``); ``timestamp`` is that clock anchored to a UTC
#: calendar day derived from ``SessionInfo.json`` (see ``ingestion.session_clock``).
WEATHER_SCHEMA: dict[str, pl.DataType] = {
    "timestamp": pl.Datetime(time_unit="us", time_zone="UTC"),
    "air_temp": pl.Float32,
    "track_temp": pl.Float32,
    "humidity": pl.Float32,
    "pressure": pl.Float32,
    "rainfall": pl.Boolean,
    "wind_direction": pl.Int32,
    "wind_speed": pl.Float32,
}

WEATHER_COLUMNS: list[str] = list(WEATHER_SCHEMA)


def empty_weather() -> pl.DataFrame:
    """Return an empty weather frame with the canonical schema."""
    return pl.DataFrame(schema=WEATHER_SCHEMA)


#: One track-status change event. ``status`` follows the F1 feed's numeric-string
#: codes (``"1"`` AllClear, ``"2"`` Yellow, ``"4"`` SCDeployed, ``"5"`` Red,
#: ``"6"`` VSCDeployed, ``"7"`` VSCEnding). ``timestamp`` — see :data:`WEATHER_SCHEMA`.
TRACK_STATUS_SCHEMA: dict[str, pl.DataType] = {
    "timestamp": pl.Datetime(time_unit="us", time_zone="UTC"),
    "status": pl.Utf8,
    "message": pl.Utf8,
}


def empty_track_status() -> pl.DataFrame:
    """Return an empty track-status frame with the canonical schema."""
    return pl.DataFrame(schema=TRACK_STATUS_SCHEMA)


#: One session-status transition (``Inactive``/``Started``/``Aborted``/``Finished``/
#: ``Finalised``/``Ends``). ``timestamp`` — see :data:`WEATHER_SCHEMA`.
SESSION_STATUS_SCHEMA: dict[str, pl.DataType] = {
    "timestamp": pl.Datetime(time_unit="us", time_zone="UTC"),
    "status": pl.Utf8,
}


def empty_session_status() -> pl.DataFrame:
    """Return an empty session-status frame with the canonical schema."""
    return pl.DataFrame(schema=SESSION_STATUS_SCHEMA)


#: One race control message (flags, investigations, penalties, etc.).
RACE_CONTROL_SCHEMA: dict[str, pl.DataType] = {
    "timestamp": pl.Datetime(time_unit="us", time_zone="UTC"),
    "category": pl.Utf8,
    "message": pl.Utf8,
    "flag": pl.Utf8,
    "scope": pl.Utf8,
    "sector": pl.Int32,
    "lap": pl.Int32,
}


def empty_race_control_messages() -> pl.DataFrame:
    """Return an empty race-control-messages frame with the canonical schema."""
    return pl.DataFrame(schema=RACE_CONTROL_SCHEMA)


#: One event (Grand Prix weekend) on the season calendar, from ``Index.json``.
EVENT_SCHEMA: dict[str, pl.DataType] = {
    "round": pl.Int32,
    "event_key": pl.Utf8,
    "name": pl.Utf8,
    "official_name": pl.Utf8,
    "location": pl.Utf8,
    "country": pl.Utf8,
    "start_date": pl.Datetime(time_unit="us"),
    "end_date": pl.Datetime(time_unit="us"),
}

EVENT_COLUMNS: list[str] = list(EVENT_SCHEMA)


def empty_events() -> pl.DataFrame:
    """Return an empty event-schedule frame with the canonical schema."""
    return pl.DataFrame(schema=EVENT_SCHEMA)


#: One session (FP1/Q/R/...) within an event, from ``Index.json``.
EVENT_SESSION_SCHEMA: dict[str, pl.DataType] = {
    "round": pl.Int32,
    "session_name": pl.Utf8,
    "session_type": pl.Utf8,
    "start_date": pl.Datetime(time_unit="us"),
    "path": pl.Utf8,
}


def empty_event_sessions() -> pl.DataFrame:
    """Return an empty event-sessions frame with the canonical schema."""
    return pl.DataFrame(schema=EVENT_SESSION_SCHEMA)


#: One driver's championship standing (jolpica-f1/Ergast — or T1API, which mixes
#: livetiming + Ergast sources per its own docs).
DRIVER_STANDINGS_SCHEMA: dict[str, pl.DataType] = {
    "position": pl.Int32,
    "driver": pl.Utf8,
    "driver_id": pl.Utf8,
    "full_name": pl.Utf8,
    "team": pl.Utf8,
    "nationality": pl.Utf8,
    "points": pl.Float32,
    "wins": pl.Int32,
}


def empty_driver_standings() -> pl.DataFrame:
    """Return an empty driver-standings frame with the canonical schema."""
    return pl.DataFrame(schema=DRIVER_STANDINGS_SCHEMA)


#: One constructor's championship standing.
CONSTRUCTOR_STANDINGS_SCHEMA: dict[str, pl.DataType] = {
    "position": pl.Int32,
    "team": pl.Utf8,
    "team_id": pl.Utf8,
    "nationality": pl.Utf8,
    "points": pl.Float32,
    "wins": pl.Int32,
}


def empty_constructor_standings() -> pl.DataFrame:
    """Return an empty constructor-standings frame with the canonical schema."""
    return pl.DataFrame(schema=CONSTRUCTOR_STANDINGS_SCHEMA)


#: One driver's classified result for a single race (jolpica-f1/Ergast).
#:
#: ``time``/``fastest_lap_time`` are kept as the raw Ergast strings (e.g.
#: ``"+1.234"`` for a gap, ``"1:32:07.043"`` for the leader) rather than parsed
#: durations — Ergast's ``Time`` field format differs for the leader vs. others and
#: is absent for non-finishers, so a single Duration column would need to be mostly
#: null anyway.
ERGAST_RESULTS_SCHEMA: dict[str, pl.DataType] = {
    "position": pl.Int32,
    "driver": pl.Utf8,
    "driver_id": pl.Utf8,
    "team": pl.Utf8,
    "grid": pl.Int32,
    "laps": pl.Int32,
    "status": pl.Utf8,
    "points": pl.Float32,
    "time": pl.Utf8,
    "fastest_lap_rank": pl.Int32,
    "fastest_lap_time": pl.Utf8,
}


def empty_ergast_results() -> pl.DataFrame:
    """Return an empty Ergast race-results frame with the canonical schema."""
    return pl.DataFrame(schema=ERGAST_RESULTS_SCHEMA)


#: One circuit corner (T1API/premium only — the free F1 feed carries no static
#: circuit geometry). Mirrors fastf1's well-known ``CircuitInfo.corners`` shape.
CIRCUIT_CORNER_SCHEMA: dict[str, pl.DataType] = {
    "number": pl.Int32,
    "letter": pl.Utf8,
    "x": pl.Float32,
    "y": pl.Float32,
    "angle": pl.Float32,
    "distance": pl.Float32,
}


def empty_circuit_corners() -> pl.DataFrame:
    """Return an empty circuit-corners frame with the canonical schema."""
    return pl.DataFrame(schema=CIRCUIT_CORNER_SCHEMA)
