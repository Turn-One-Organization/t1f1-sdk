# t1f1-sdk Documentation

`t1f1-sdk` is a Formula 1 telemetry SDK for working with session data, analysis products,
event metadata, standings, and circuit information through a small Python API.

> **For AI agents / quick lookups:** every API reference page below lists exact
> signatures, return schemas, and a runnable example for every public function or
> method — no page requires reading source to use correctly. The
> [Full API Index](#full-api-index) at the bottom of this page is a flat table of
> every public symbol and its import path, meant for fast scanning. The
> [Schemas](api-reference/schemas.md) page is a complete data dictionary (every
> column name/type this SDK returns, anywhere) if you need to know exact field
> names before writing code against a frame.

This documentation is organized around the SDK user journey:

1. Install the package and make your first request.
2. Learn how free and premium access differ.
3. Explore the `Client` and `Session` APIs.
4. Use the reference pages when you need exact method behavior or return types.

## Start Here

- [Installation](getting-started/installation.md)
- [Authentication](getting-started/authentication.md)
- [Quickstart](getting-started/quickstart.md)
- [Migrating from fastf1](getting-started/migration-from-fastf1.md)

## Core APIs

- [Client API](api-reference/client.md)
- [Session API](api-reference/session.md)
- [Frames API](api-reference/frames.md) — `LapsFrame`, telemetry transforms, `delta_time`
- [Analysis API](api-reference/analysis.md)
- [Events API](api-reference/events.md)
- [Circuits API](api-reference/circuits.md)
- [Cache API](api-reference/cache.md)
- [Plotting API](api-reference/plotting.md)
- [Schemas](api-reference/schemas.md) — full data dictionary of every returned frame
- [Errors](api-reference/errors.md)

## Tutorials

- [Plotting with matplotlib](tutorials/matplotlib-plots.md) — race pace, tyre stints,
  and speed-trace comparison charts, built on the analysis + plotting-token APIs.

## Concepts

- [Overview](concepts/overview.md)
- [Free vs Premium](concepts/free-vs-premium.md)
- [Sync vs Async](concepts/sync-vs-async.md)
- [Data Shapes](concepts/data-shapes.md)
- [Caching](concepts/caching.md)

## Reference

- [Configuration](reference/configuration.md)
- [Glossary](reference/glossary.md)
- [FAQ](reference/faq.md)

## What the SDK Covers

- Raw telemetry and session data from the free F1 live-timing feed.
- Derived analysis products such as speed, pace, comparison, and stint views.
- Event, standings, and circuit metadata.
- Blocking and async entrypoints with matching behavior.

## Public Surface

The primary entrypoints are `Client` and `AsyncClient` from `t1f1`.

The main session-level workflow is:

```python
from t1f1 import Client

with Client() as client:
    session = client.session(2024, "Monza", "Q")
    telemetry = session.telemetry("VER")
    print(telemetry.head())
```

If you have an API key, the same API can also route premium analysis methods to
`api.t1f1.com`.

## Full API Index

Every public symbol, its import path, and what it does — the flat, complete list.
For prose/examples, follow the link in the "Docs" column.

### `t1f1` (top-level)

| Symbol | Import | Docs |
|---|---|---|
| `Client` | `from t1f1 import Client` | [Client API](api-reference/client.md) |
| `AsyncClient` | `from t1f1 import AsyncClient` | [Client API](api-reference/client.md) |
| `ClientConfig` | `from t1f1 import ClientConfig` | [Configuration](reference/configuration.md) |
| `T1F1Error` | `from t1f1 import T1F1Error` | [Errors](api-reference/errors.md) |
| `AuthError` | `from t1f1 import AuthError` | [Errors](api-reference/errors.md) |
| `RateLimitError` | `from t1f1 import RateLimitError` | [Errors](api-reference/errors.md) |
| `SessionNotFoundError` | `from t1f1 import SessionNotFoundError` | [Errors](api-reference/errors.md) |
| `DataNotAvailableError` | `from t1f1 import DataNotAvailableError` | [Errors](api-reference/errors.md) |
| `UpstreamUnavailableError` | `from t1f1 import UpstreamUnavailableError` | [Errors](api-reference/errors.md) |
| `__version__` | `from t1f1 import __version__` | — |

### `Client`/`AsyncClient` methods & properties

| Member | Docs |
|---|---|
| `session(year, gp, session)` | [Client API](api-reference/client.md#sessionyear-gp-session---session) |
| `event_schedule(year)` | [Client API](api-reference/client.md#event_schedule) |
| `event(year, gp)` | [Client API](api-reference/client.md#eventyear-int-gp-int--str---dict) |
| `event_sessions(year, gp)` | [Client API](api-reference/client.md#event_sessionsyear-int-gp-int--str---pldataframe) |
| `events_remaining(year, after=None)` | [Client API](api-reference/client.md#events_remainingyear-int-after-datetime--none--none---pldataframe) |
| `driver_standings(year, round=None)` | [Client API](api-reference/client.md#driver_standingsyear-int-round-int--none--none---pldataframe) |
| `constructor_standings(year, round=None)` | [Client API](api-reference/client.md#constructor_standingsyear-int-round-int--none--none---pldataframe) |
| `race_results(year, round)` | [Client API](api-reference/client.md#race_resultsyear-int-round-int---pldataframe) |
| `circuit_info(circuit_id, year=None)` | [Circuits API](api-reference/circuits.md) |
| `circuits(year)` | [Circuits API](api-reference/circuits.md) |
| `is_premium` / `quota` / `last_source` | [Client API](api-reference/client.md#properties) |

### `Session`/`AsyncSession` methods & properties

| Member | Docs |
|---|---|
| `telemetry(driver)` | [Session API](api-reference/session.md#telemetrydriver-str---pldataframe) |
| `lap_telemetry(driver, lap_number)` | [Session API](api-reference/session.md#lap_telemetrydriver-str-lap_number-int---pldataframe) |
| `driver_ahead(driver)` | [Session API](api-reference/session.md#driver_aheaddriver-str---pldataframe) |
| `laps()` | [Session API](api-reference/session.md#laps---lapsframe) |
| `results()` | [Session API](api-reference/session.md#results---pldataframe) |
| `weather()` | [Session API](api-reference/session.md#weather---pldataframe) |
| `race_control_messages()` | [Session API](api-reference/session.md#race_control_messages---pldataframe) |
| `track_status()` | [Session API](api-reference/session.md#track_status---pldataframe) |
| `session_status()` | [Session API](api-reference/session.md#session_status---pldataframe) |
| `total_laps()` | [Session API](api-reference/session.md#total_laps---int--none) |
| `load(...)` | [Session API](api-reference/session.md#load--optional-concurrent-prefetch) |
| `top_speeds()` | [Session API](api-reference/session.md#top_speeds---pldataframe) |
| `speed_trap_top_speeds()` | [Session API](api-reference/session.md#speed_trap_top_speeds---pldataframe) |
| `driver_pace(threshold=1.07)` | [Session API](api-reference/session.md#driver_pace-threshold-float--107---pldataframe) |
| `teams_pace(threshold=1.07)` | [Session API](api-reference/session.md#teams_pace-threshold-float--107---pldataframe) |
| `tyre_stints()` | [Session API](api-reference/session.md#tyre_stints---pldataframe) |
| `qualifying_results()` | [Session API](api-reference/session.md#qualifying_results---pldataframe) |
| `speed_distribution(driver=None, bins=20)` | [Session API](api-reference/session.md#speed_distributiondriver-str--none-none--bins-int--20---pldataframe) |
| `compare(driver1, driver2, lap1=None, lap2=None)` | [Session API](api-reference/session.md#comparedriver1-driver2--lap1none-lap2none---pldataframe) |
| `throttle_comparison(...)` | [Session API](api-reference/session.md#throttle_comparisondriver1-driver2--lap1none-lap2none---pldataframe) |
| `lap_time_analysis(...)` | [Session API](api-reference/session.md#lap_time_analysisdriver1-driver2--lap1none-lap2none---pldataframe) |
| `track_dominance(...)` | [Session API](api-reference/session.md#track_dominancedriver1-driver2--lap1none-lap2none-n_minisectors25---pldataframe) |
| `is_premium` / `last_source` | [Session API](api-reference/session.md#identity--state) |

### `t1f1.frames.laps.LapsFrame`

| Member | Docs |
|---|---|
| `pick_drivers` / `pick_teams` / `pick_compounds` / `pick_laps` / `pick_track_status` | [Frames API](api-reference/frames.md#selection) |
| `pick_not_deleted` / `pick_accurate` / `pick_wo_box` / `pick_box_laps` / `pick_quicklaps` / `pick_fastest` | [Frames API](api-reference/frames.md#quality-filters) |
| `split_qualifying_sessions` / `iterlaps` / `to_polars` | [Frames API](api-reference/frames.md#grouping--iteration) |

### `t1f1.frames.telemetry` (pure functions)

| Function | Docs |
|---|---|
| `add_distance`, `add_differential_distance`, `add_relative_distance` | [Frames API](api-reference/frames.md#t1f1framestelemetry--pure-transform-functions) |
| `add_track_status`, `merge_channels` | same |
| `slice_by_time`, `slice_by_mask`, `resample_channels`, `fill_missing` | same |
| `compute_driver_ahead` | same |

### `t1f1.utils` / `t1f1.analysis` (pure functions)

| Function | Docs |
|---|---|
| `delta_time(reference, comparison)` | [Frames API](api-reference/frames.md#t1f1utilsdelta_time) |
| `speed_trap_top_speeds(laps)` | [Analysis API](api-reference/analysis.md) |
| `driver_pace(laps, threshold=1.07)` | [Analysis API](api-reference/analysis.md) |
| `teams_pace(laps, threshold=1.07)` | [Analysis API](api-reference/analysis.md) |
| `tyre_stints(laps)` | [Analysis API](api-reference/analysis.md) |
| `qualifying_results(results)` | [Analysis API](api-reference/analysis.md) |
| `speed_distribution(telemetry, bins=20)` | [Analysis API](api-reference/analysis.md) |
| `compare(tel1, tel2)` | [Analysis API](api-reference/analysis.md) |
| `track_dominance(tel1, tel2, driver1=, driver2=, n_minisectors=25)` | [Analysis API](api-reference/analysis.md) |

### `t1f1.plotting` (pure functions/tokens)

| Symbol | Docs |
|---|---|
| `get_team_color`, `get_compound_color`, `get_driver_color`, `get_driver_style` | [Plotting API](api-reference/plotting.md) |
| `driver_team_map` | [Plotting API](api-reference/plotting.md) |
| `TEAM_COLORS`, `COMPOUND_COLORS`, `FALLBACK_COLOR`, `LINESTYLES` | [Plotting API](api-reference/plotting.md) |

### `t1f1.cache`

| Symbol | Docs |
|---|---|
| `enable_cache(path, ttl=None)` | [Cache API](api-reference/cache.md) |
| `DiskCache`, `RedisCache`, `CacheBackend` | [Cache API](api-reference/cache.md) |

### `t1f1.schemas`

All `*_SCHEMA` constants and matching `empty_*()` functions — see the full data
dictionary at [Schemas](api-reference/schemas.md).