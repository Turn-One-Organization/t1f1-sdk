# Schemas — data dictionary

Every frame the SDK returns has a fixed, typed `polars` schema — even when empty
(you get a zero-row frame with the right columns/dtypes, never a `None` or a raised
error for "no data"). This page lists every schema, its exact column names/types,
and which method(s) return it. Import any schema constant directly if you want to
validate/cast your own data against it, or check `some_frame.schema == SCHEMA`.

```python
from t1f1.schemas import TELEMETRY_SCHEMA, LAP_SCHEMA, RESULTS_SCHEMA  # etc.
```

Column names are `snake_case` throughout (the raw feed's `CamelCase` is normalized
during decoding). Duration columns (`lap_time`, `q1`, ...) are `pl.Duration("ms")`,
not Python `timedelta` or pandas `Timedelta` objects — use `.dt.total_seconds()` if
you need a plain float.

## `TELEMETRY_SCHEMA`

Returned by: `session.telemetry()`, `session.lap_telemetry()`, `session.driver_ahead()`.

| Column | Type | Meaning |
|---|---|---|
| `timestamp` | `Datetime("us", "UTC")` | Sample time. |
| `driver` | `Utf8` | Driver TLA, e.g. `"VER"`. |
| `driver_number` | `Utf8` | Racing number as a string, e.g. `"1"`. |
| `speed_kmh` | `Float32` | Speed, km/h. |
| `rpm` | `Int32` | Engine RPM. |
| `gear` | `Int8` | 0 (neutral) to 8. |
| `throttle` | `Float32` | 0-100 %. |
| `brake` | `Float32` | 0-100 % (or 0/1 on some sessions — raw feed inconsistency). |
| `drs` | `Int8` | Raw DRS indicator from the feed. |
| `distance` | `Float32` | Cumulative distance, meters, from the first sample. |
| `x`, `y`, `z` | `Float32` | Position, in 1/10 m (F1's raw units). |

`driver_ahead()` telemetry additionally carries `driver_ahead: Utf8` and
`distance_to_driver_ahead: Float32`.

## `LAP_SCHEMA`

Returned by: `session.laps()` (wrapped in a `LapsFrame` — `.to_polars()` for the raw frame).

| Column | Type | Meaning |
|---|---|---|
| `lap_number` | `Int32` | 1-indexed. |
| `driver` | `Utf8` | TLA. |
| `driver_number` | `Utf8` | Racing number as a string. |
| `team` | `Utf8` | Team name. |
| `lap_time` | `Duration("ms")` | Total lap time. |
| `lap_start_time` | `Datetime("us", "UTC")` | When this lap started. |
| `sector1_time`, `sector2_time`, `sector3_time` | `Duration("ms")` | Per-sector times. |
| `speed_i1`, `speed_i2`, `speed_fl`, `speed_st` | `Float32` | Speed-trap readings (intermediate 1/2, finish line, speed trap), km/h. |
| `is_personal_best` | `Boolean` | Whether this was the driver's personal best at the time. |
| `compound` | `Utf8` | Tyre compound, e.g. `"SOFT"`. |
| `tyre_life` | `Int32` | Laps completed on the current tyre set. |
| `fresh_tyre` | `Boolean` | Whether the stint started on a new tyre set. |
| `stint` | `Int32` | Stint number (1-indexed). |
| `pit_out_time`, `pit_in_time` | `Datetime("us", "UTC")` | Null unless this lap involved a pit stop. |
| `position` | `Int32` | Track position at lap completion. |
| `track_status` | `Utf8` | Track-status code active during this lap. |
| `deleted` | `Boolean` | Whether the lap time was deleted by stewards. |
| `deleted_reason` | `Utf8` | Free text, if deleted. |
| `is_accurate` | `Boolean` | Feed-reported accuracy flag. |

`qualifying_results()`/`session.qualifying_results()` add a `gap_to_pole:
Duration("ms")` column on top of `RESULTS_SCHEMA` (below), not this one.

## `RESULTS_SCHEMA`

Returned by: `session.results()`, `session.qualifying_results()` (plus `gap_to_pole`).

| Column | Type | Meaning |
|---|---|---|
| `driver` | `Utf8` | TLA. |
| `driver_number` | `Utf8` | Racing number as a string. |
| `team` | `Utf8` | Team name. |
| `position` | `Int32` | Final classified position. |
| `classified_position` | `Utf8` | String, since non-finishers classify as `"R"`/`"D"`/`"NC"` etc., not a number. |
| `grid_position` | `Int32` | Starting grid slot. |
| `q1`, `q2`, `q3` | `Duration("ms")` | Best time per qualifying segment (Qualifying/Sprint Qualifying sessions only; null for Race/Practice). |
| `time` | `Duration("ms")` | Race time, if applicable. |
| `status` | `Utf8` | `"Finished"` / `"Retired"` / `"Stopped"`. |
| `points` | `Float32` | Championship points scored. |

## `WEATHER_SCHEMA`

Returned by: `session.weather()`.

| Column | Type | Meaning |
|---|---|---|
| `timestamp` | `Datetime("us", "UTC")` | Sample time. |
| `air_temp`, `track_temp` | `Float32` | °C. |
| `humidity` | `Float32` | %. |
| `pressure` | `Float32` | mbar. |
| `rainfall` | `Boolean` | Whether it's currently raining. |
| `wind_direction` | `Int32` | Degrees. |
| `wind_speed` | `Float32` | m/s. |

## `TRACK_STATUS_SCHEMA`

Returned by: `session.track_status()`.

| Column | Type | Meaning |
|---|---|---|
| `timestamp` | `Datetime("us", "UTC")` | Change time. |
| `status` | `Utf8` | Numeric-string code: `"1"` AllClear, `"2"` Yellow, `"4"` Safety Car, `"5"` Red, `"6"` VSC Deployed, `"7"` VSC Ending. |
| `message` | `Utf8` | Human-readable status text. |

## `SESSION_STATUS_SCHEMA`

Returned by: `session.session_status()`.

| Column | Type | Meaning |
|---|---|---|
| `timestamp` | `Datetime("us", "UTC")` | Transition time. |
| `status` | `Utf8` | `Inactive` / `Started` / `Aborted` / `Finished` / `Finalised` / `Ends`. |

## `RACE_CONTROL_SCHEMA`

Returned by: `session.race_control_messages()`.

| Column | Type | Meaning |
|---|---|---|
| `timestamp` | `Datetime("us", "UTC")` | Message time. |
| `category` | `Utf8` | e.g. `"Flag"`, `"Drs"`, `"CarEvent"`. |
| `message` | `Utf8` | Full message text. |
| `flag` | `Utf8` | Flag color, if applicable (`"YELLOW"`, `"GREEN"`, ...). |
| `scope` | `Utf8` | `"Track"` / `"Sector"` / `"Driver"`. |
| `sector` | `Int32` | Sector number, if `scope="Sector"`. |
| `lap` | `Int32` | Lap number, if applicable. |

## `EVENT_SCHEMA`

Returned by: `client.event_schedule()`, `client.events_remaining()`.

| Column | Type | Meaning |
|---|---|---|
| `round` | `Int32` | **Positional** index into the season's `Index.json` — see the [Events API](events.md#a-note-on-round-numbers) caveat, not guaranteed to equal the real FIA round number for a partial season. |
| `event_key` | `Utf8` | The feed's internal event key. |
| `name`, `official_name` | `Utf8` | Event names. |
| `location` | `Utf8` | Circuit/city. |
| `country` | `Utf8` | Country name. |
| `start_date`, `end_date` | `Datetime("us")` (naive, local circuit time) | Event weekend bounds. |

## `EVENT_SESSION_SCHEMA`

Returned by: `client.event_sessions()`.

| Column | Type | Meaning |
|---|---|---|
| `round` | `Int32` | Same caveat as above. |
| `session_name`, `session_type` | `Utf8` | e.g. `"Qualifying"`, `"Qualifying"`. |
| `start_date` | `Datetime("us")` (naive) | Session start, local circuit time. |
| `path` | `Utf8` | The live-timing feed's relative path for this session. |

## `DRIVER_STANDINGS_SCHEMA`

Returned by: `client.driver_standings()`.

| Column | Type | Meaning |
|---|---|---|
| `position` | `Int32` | Standing position. |
| `driver` | `Utf8` | TLA (Ergast `code` / T1API `driver_code`). |
| `driver_id` | `Utf8` | Ergast's `driverId` slug; `None` when sourced from T1API. |
| `full_name` | `Utf8` | Driver's full name. |
| `team` | `Utf8` | Current/most recent team. |
| `nationality` | `Utf8` | |
| `points` | `Float32` | |
| `wins` | `Int32` | |

## `CONSTRUCTOR_STANDINGS_SCHEMA`

Returned by: `client.constructor_standings()`.

| Column | Type | Meaning |
|---|---|---|
| `position` | `Int32` | |
| `team` | `Utf8` | |
| `team_id` | `Utf8` | Ergast's `constructorId` slug; `None` from T1API. |
| `nationality` | `Utf8` | |
| `points` | `Float32` | |
| `wins` | `Int32` | |

## `ERGAST_RESULTS_SCHEMA`

Returned by: `client.race_results()` (always Ergast — no T1API equivalent).

| Column | Type | Meaning |
|---|---|---|
| `position` | `Int32` | |
| `driver`, `driver_id` | `Utf8` | TLA and Ergast's `driverId` slug. |
| `team` | `Utf8` | |
| `grid` | `Int32` | Starting grid position. |
| `laps` | `Int32` | Laps completed. |
| `status` | `Utf8` | e.g. `"Finished"`, `"+1 Lap"`, `"Retired"`. |
| `points` | `Float32` | |
| `time` | `Utf8` | **Raw Ergast string**, not a parsed `Duration` — the leader's absolute time and others' gaps (`"+1.234"`) use different formats and are absent for non-finishers, so this stays a string rather than a mostly-null Duration column. |
| `fastest_lap_rank` | `Int32` | |
| `fastest_lap_time` | `Utf8` | Same "raw string" reasoning as `time`. |

## `CIRCUIT_CORNER_SCHEMA`

Returned by: `CircuitInfo.corners` (from `client.circuit_info()`, premium only).

| Column | Type | Meaning |
|---|---|---|
| `number` | `Int32` | Corner number. |
| `letter` | `Utf8` | Sub-corner letter (`"a"`, `"b"`), or `""`. |
| `x`, `y` | `Float32` | Track-map coordinates. |
| `angle` | `Float32` | Label rotation angle. |
| `distance` | `Float32` | Distance from the start/finish line, meters. |

## Analysis output schemas

`t1f1.analysis`'s functions (and the matching `Session` methods) return their own
schemas — `PACE_SCHEMA`, `TEAM_PACE_SCHEMA`, `STINT_SCHEMA`, `SPEED_TRAP_SCHEMA`,
`SPEED_DISTRIBUTION_SCHEMA`, `COMPARE_SCHEMA`, `TRACK_DOMINANCE_SCHEMA` — documented
inline on the [Analysis API](analysis.md) page next to each function, since their
column sets are specific to that one function's output.

## Empty-frame helpers

Every schema above has a matching `empty_*()` function (`empty_telemetry()`,
`empty_laps()`, `empty_results()`, `empty_weather()`, `empty_track_status()`,
`empty_session_status()`, `empty_race_control_messages()`, `empty_events()`,
`empty_event_sessions()`, `empty_driver_standings()`, `empty_constructor_standings()`,
`empty_ergast_results()`, `empty_circuit_corners()`) — a zero-row frame with the
correct schema, useful in tests or as a default value:

```python
from t1f1.schemas import empty_laps

def summarize(laps: pl.DataFrame = None):
    laps = laps if laps is not None else empty_laps()
    ...
```
