# Analysis API

Analysis products are available two ways:

1. **On the session** (`session.driver_pace()`, ...) — the normal path. Premium if
   keyed, otherwise computed locally. See [Session API](session.md#derived-analysis--premium-if-keyed-else-computed-locally).
2. **As pure functions in `t1f1.analysis`** — the same free-tier computation,
   callable directly on frames you already have (e.g. after filtering/combining
   `laps()` yourself). No network, no session object, fully offline-testable.

```python
from t1f1 import analysis
```

Every function below is pure: it takes already-fetched frames (`laps()`,
`results()`, `telemetry()`) and returns a new `pl.DataFrame` — safe to call
repeatedly, safe to unit test with a synthetic frame, no I/O.

## `speed_trap_top_speeds(laps: pl.DataFrame) -> pl.DataFrame`

Peak official speed-trap reading (`speed_st`) per driver. Output:
`driver, lap_number, top_speed_kmh`.

```python
laps = session.laps().to_polars()
print(analysis.speed_trap_top_speeds(laps))
```

## `driver_pace(laps: pl.DataFrame, *, threshold: float = 1.07) -> pl.DataFrame`

Box-and-whisker pace per driver over quicklaps (within `threshold` x the
session-best lap), excluding deleted and in/out laps. Output:
`driver, laps, min, q1, median, q3, max` (all lap-time columns are `Duration("ms")`).

```python
print(analysis.driver_pace(laps))
print(analysis.driver_pace(laps, threshold=1.03))  # tighter cutoff
```

## `teams_pace(laps: pl.DataFrame, *, threshold: float = 1.07) -> pl.DataFrame`

Same as `driver_pace`, grouped by `team`. Output: `team, laps, min, q1, median, q3, max`.

```python
print(analysis.teams_pace(laps))
```

## `tyre_stints(laps: pl.DataFrame) -> pl.DataFrame`

Per-driver stint timeline. Output:
`driver, team, stint, compound, start_lap, end_lap, lap_count`.

```python
stints = analysis.tyre_stints(laps)
print(stints.filter(stints["driver"] == "VER"))
```

## `qualifying_results(results: pl.DataFrame) -> pl.DataFrame`

`results()` with a `gap_to_pole` column added (best of Q3/Q2/Q1 minus the pole
time), sorted by `position`.

```python
results = session.results()
print(analysis.qualifying_results(results).select("position", "driver", "gap_to_pole"))
```

## `speed_distribution(telemetry: pl.DataFrame, *, bins: int = 20) -> pl.DataFrame`

Histogram of `speed_kmh`. Output: `bin_start, bin_end, count`.

```python
tel = session.telemetry("VER")
hist = analysis.speed_distribution(tel, bins=30)
```

## `compare(tel1: pl.DataFrame, tel2: pl.DataFrame) -> pl.DataFrame`

Distance-aligned comparison of two laps' telemetry (each already sliced to one lap,
e.g. via `session.lap_telemetry`) plus a time delta from
[`utils.delta_time`](frames.md#t1f1utilsdelta_time). Output: `distance,
delta_seconds, driver1_speed_kmh, driver2_speed_kmh, driver1_throttle,
driver2_throttle, driver1_brake, driver2_brake`. `delta_seconds` positive means
driver2 is behind at that point.

```python
tel1 = session.lap_telemetry("VER", 12)
tel2 = session.lap_telemetry("NOR", 12)
cmp = analysis.compare(tel1, tel2)
```

## `track_dominance(tel1, tel2, *, driver1, driver2, n_minisectors=25) -> pl.DataFrame`

Average speed per equal-length minisector (needs `relative_distance` — see
`t1f1.frames.telemetry.add_relative_distance`), tagging which driver was faster.
Output: `minisector, driver1_avg_speed_kmh, driver2_avg_speed_kmh, faster`.

```python
from t1f1.frames.telemetry import add_distance, add_relative_distance

tel1 = session.lap_telemetry("VER", 12).pipe(add_distance).pipe(add_relative_distance)
tel2 = session.lap_telemetry("NOR", 12).pipe(add_distance).pipe(add_relative_distance)
dominance = analysis.track_dominance(tel1, tel2, driver1="VER", driver2="NOR", n_minisectors=30)
```

(`session.track_dominance("VER", "NOR")` does this slicing for you — call the raw
function directly only when you already have prepared telemetry frames.)

## Schemas

Every function above returns a fixed, typed schema — even when the input is empty
(you get a zero-row frame with the right columns/dtypes, never an error). The schema
constants (`PACE_SCHEMA`, `TEAM_PACE_SCHEMA`, `STINT_SCHEMA`, `SPEED_TRAP_SCHEMA`,
`SPEED_DISTRIBUTION_SCHEMA`, `COMPARE_SCHEMA`, `TRACK_DOMINANCE_SCHEMA`) are in
`t1f1.analysis` if you want to inspect them directly:

```python
from t1f1.analysis import COMPARE_SCHEMA
print(COMPARE_SCHEMA)
```
