# Session API

`Session`/`AsyncSession` are the handle returned by `client.session(year, gp,
session)` — every accessor below fetches and caches on first use, so there's no
required setup step. `session.load(...)` is an *optional* performance prefetch that
gathers several streams concurrently; it changes nothing about what each accessor
returns.

```python
session = client.session(2024, "Monza", "Q")
```

## Identity & state

| Property | Type | Meaning |
|---|---|---|
| `year` | `int` | The season passed to `client.session(...)`. |
| `gp` | `int \| str` | The round/event passed to `client.session(...)`. |
| `session` | `str` | The session name passed to `client.session(...)`. |
| `is_premium` | `bool` | Whether this session has a premium (T1API) source attached. |
| `last_source` | `str \| None` | `"t1api"` or `"free"` — whichever tier served the most recently completed call under "Derived analysis" below. `None` before any such call. Not meaningful under concurrent overlapping calls (it's a simple last-write). |

```python
print(session.year, session.gp, session.session)  # 2024 Monza Q
session.driver_pace()
print(session.last_source)  # "t1api" if premium served it, "free" if it fell back
```

## `load(...)` — optional concurrent prefetch

```python
session.load(*, laps: bool = True, telemetry: bool = True, weather: bool = True, messages: bool = True) -> Session
```

Fetches the requested stream groups with `asyncio.gather` instead of one-by-one on
first access. Returns `self`, so it chains:

```python
session = client.session(2024, "Monza", "R").load(telemetry=False)  # skip CarData/Position
laps = session.laps()
```

## Raw telemetry & session data — always the free F1 feed

T1API has no raw per-sample telemetry / laps / results / weather endpoints (only
*derived analysis*, below), so these never route to premium regardless of `api_key`.

### `telemetry(driver: str) -> pl.DataFrame`

Per-sample telemetry for one driver. `driver` accepts a TLA (`"VER"`) or racing
number (`"1"`). Schema: `t1f1.schemas.TELEMETRY_SCHEMA`
(`timestamp, driver, driver_number, speed_kmh, rpm, gear, throttle, brake, drs,
distance, x, y, z`).

```python
tel = session.telemetry("VER")
print(tel.select("timestamp", "speed_kmh", "throttle", "gear").head())
print(tel["speed_kmh"].max())  # peak speed this session
```

### `lap_telemetry(driver: str, lap_number: int) -> pl.DataFrame`

Telemetry sliced to one lap's time window, with `distance`/`relative_distance`
recomputed lap-relative (0 at the lap's start). See the docstring caveat about laps
following a long red-flag/pit gap being less precise.

```python
lap5 = session.lap_telemetry("VER", 5)
print(lap5["distance"].max())  # ~ the circuit's lap length in meters
```

### `driver_ahead(driver: str) -> pl.DataFrame`

`driver`'s telemetry augmented with `driver_ahead`/`distance_to_driver_ahead`,
computed against every other driver's session telemetry. Noticeably more expensive
than `telemetry()` since it fetches every driver.

```python
battle = session.driver_ahead("VER")
print(battle.select("timestamp", "driver_ahead", "distance_to_driver_ahead"))
```

### `laps() -> LapsFrame`

One row per completed lap, for every driver. Returns a `LapsFrame` (a chainable
wrapper — see [Frames API](frames.md)); `.to_polars()` for the raw `pl.DataFrame`.
Schema: `t1f1.schemas.LAP_SCHEMA`.

```python
laps = session.laps()
ver_fastest = laps.pick_drivers("VER").pick_fastest().to_polars()
print(ver_fastest["lap_time"])
```

### `results() -> pl.DataFrame`

Session classification. Schema: `t1f1.schemas.RESULTS_SCHEMA`.

```python
results = session.results()
print(results.select("position", "driver", "team", "q1", "q2", "q3"))
```

### `weather() -> pl.DataFrame`

One row per weather sample. Schema: `t1f1.schemas.WEATHER_SCHEMA`.

```python
weather = session.weather()
print(weather.select("timestamp", "air_temp", "track_temp", "rainfall"))
```

### `race_control_messages() -> pl.DataFrame`

Flags, investigations, penalties. Schema: `t1f1.schemas.RACE_CONTROL_SCHEMA`.

```python
messages = session.race_control_messages()
print(messages.filter(messages["flag"] == "YELLOW"))
```

### `track_status() -> pl.DataFrame`

Track status changes (green/yellow/SC/VSC/red). Schema:
`t1f1.schemas.TRACK_STATUS_SCHEMA`.

```python
status = session.track_status()
```

### `session_status() -> pl.DataFrame`

Session lifecycle transitions (`Started`/`Aborted`/`Finished`/...). Schema:
`t1f1.schemas.SESSION_STATUS_SCHEMA`.

```python
status = session.session_status()
```

### `total_laps() -> int | None`

Total scheduled laps for a Race session (from `LapCount.jsonStream`, falling back to
the max `lap_number` seen). `None` for non-Race sessions where neither is available.

```python
print(session.total_laps())  # 53
```

## Derived analysis — premium if keyed, else computed locally

Every method below tries the premium (T1API) source first when the client was
constructed with `api_key`, and **gracefully falls back** to local free-tier compute
if premium fails with a retryable error (outage, rate limit, "not published yet") —
see [Free vs Premium](../concepts/free-vs-premium.md). A rejected API key raises
`AuthError` instead of silently falling back.

### `top_speeds() -> pl.DataFrame`

Peak instantaneous CarData speed per driver, for the whole session.

```python
print(session.top_speeds())
# shape: (20, 2)  driver | top_speed_kmh
```

### `speed_trap_top_speeds() -> pl.DataFrame`

Peak *official speed-trap* reading (`speed_st`) per driver, from `laps()` — distinct
from `top_speeds()`, which uses continuous CarData instead of the fixed trap point.

```python
print(session.speed_trap_top_speeds())
# shape: (20, 3)  driver | lap_number | top_speed_kmh
```

### `driver_pace(*, threshold: float = 1.07) -> pl.DataFrame`

Box-and-whisker pace stats per driver over "quicklaps" (within `threshold` x the
session-best lap — the 107% rule by default), excluding deleted and in/out laps.

```python
pace = session.driver_pace()
print(pace.select("driver", "laps", "min", "median", "max"))

# A tighter cutoff — only genuinely representative race-pace laps
pace_tight = session.driver_pace(threshold=1.03)
```

### `teams_pace(*, threshold: float = 1.07) -> pl.DataFrame`

Same stats, grouped by team instead of driver.

```python
print(session.teams_pace())
```

### `tyre_stints() -> pl.DataFrame`

Per-driver stint timeline: compound, start/end lap, lap count.

```python
stints = session.tyre_stints()
print(stints.filter(stints["driver"] == "VER"))
```

### `qualifying_results() -> pl.DataFrame`

`results()` with a `gap_to_pole` column added, computed from the best of Q3/Q2/Q1
(whichever a driver actually reached), sorted by that gap.

```python
quali = session.qualifying_results()
print(quali.select("position", "driver", "gap_to_pole"))
```

### `speed_distribution(driver: str | None = None, *, bins: int = 20) -> pl.DataFrame`

Histogram of `speed_kmh` samples — one driver, or every driver's telemetry combined
if `driver=None`.

```python
hist = session.speed_distribution("VER", bins=30)
print(hist.select("bin_start", "bin_end", "count"))
```

### `compare(driver1, driver2, *, lap1=None, lap2=None) -> pl.DataFrame`

Distance-aligned speed/throttle/brake comparison of two laps (each driver's fastest
lap by default) plus a time delta. **Premium only covers "fastest lap"** — passing
an explicit `lap1`/`lap2` always uses local compute, even when keyed. Can return an
empty frame if the resolved lap falls outside the archived CarData window (a known
free-feed coverage-gap limitation, not a bug — see `RawF1Source.compare`'s
docstring).

```python
cmp = session.compare("VER", "NOR")
print(cmp.select("distance", "delta_seconds", "driver1_speed_kmh", "driver2_speed_kmh"))

# Explicit laps instead of "fastest"
cmp = session.compare("VER", "NOR", lap1=12, lap2=12)
```

### `throttle_comparison(driver1, driver2, *, lap1=None, lap2=None) -> pl.DataFrame`

`compare()` narrowed to `distance, delta_seconds, driver1_throttle, driver2_throttle`.

```python
print(session.throttle_comparison("VER", "NOR"))
```

### `lap_time_analysis(driver1, driver2, *, lap1=None, lap2=None) -> pl.DataFrame`

`compare()` narrowed to `distance, delta_seconds, driver1_speed_kmh, driver2_speed_kmh`.

```python
print(session.lap_time_analysis("VER", "NOR"))
```

### `track_dominance(driver1, driver2, *, lap1=None, lap2=None, n_minisectors=25) -> pl.DataFrame`

Average speed per equal-length minisector for two laps, tagging which driver was
faster in each — a common fastf1-community visualization fastf1 itself doesn't ship
as a built-in.

```python
dominance = session.track_dominance("VER", "NOR", n_minisectors=30)
print(dominance.select("minisector", "faster"))
```

## Errors

Every method above raises subclasses of `t1f1.T1F1Error` — see
[Errors](errors.md).
