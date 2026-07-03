# Migrating from fastf1

A cheatsheet for `fastf1` users, mapping familiar calls onto `t1f1-sdk`'s equivalents.
The two libraries solve the same problem with different foundations — `t1f1-sdk` uses
`polars` instead of `pandas` and an async-first core instead of blocking `requests` —
so most translations aren't 1:1 renames, they're small idiom shifts.

## Session loading

```python
# fastf1
import fastf1
session = fastf1.get_session(2024, "Monza", "Q")
session.load()

# t1f1-sdk
from t1f1 import Client
session = Client().session(2024, "Monza", "Q")
session.load()  # optional — every accessor below fetches & caches on first use anyway
```

`session.load()` isn't required in `t1f1-sdk` the way it is in fastf1 — it's purely a
performance prefetch that gathers several streams concurrently. Calling
`session.telemetry("VER")` cold works fine without ever calling `load()` first.

## Telemetry & laps

| fastf1 | t1f1-sdk |
|---|---|
| `session.laps` | `session.laps()` — returns a `LapsFrame`, a thin composable wrapper around a `polars.DataFrame` (`.to_polars()` for the raw frame) |
| `session.laps.pick_driver("VER")` | `session.laps().pick_drivers("VER")` |
| `session.laps.pick_quicklaps()` | `session.laps().pick_quicklaps(threshold=1.07)` |
| `lap.get_car_data()` / `lap.get_telemetry()` | `session.lap_telemetry("VER", lap_number)` |
| `session.car_data["44"]` | `session.telemetry("VER")` (accepts TLA or racing number) |
| `Telemetry.add_distance()` | `t1f1.frames.telemetry.add_distance(tel)` — pure function, `.pipe()`-able, not a bound method |
| `fastf1.utils.delta_time(ref_lap, comp_lap)` | `t1f1.utils.delta_time(ref_tel, comp_tel)` — takes telemetry frames directly, not `Lap` objects |

The biggest structural difference: fastf1's `Telemetry` is a `DataFrame` *subclass* with
bound methods (`tel.add_distance()`). `t1f1-sdk` deliberately avoids subclassing
`DataFrame` (`polars` discourages it) — transforms in `t1f1.frames.telemetry` are pure
functions you compose with `.pipe()`:

```python
from t1f1.frames.telemetry import add_distance, add_relative_distance

tel = session.telemetry("VER").pipe(add_distance).pipe(add_relative_distance)
```

## Results & standings

| fastf1 | t1f1-sdk |
|---|---|
| `session.results` | `session.results()` |
| `fastf1.ergast.Ergast().get_driver_standings(season=2024)` | `client.driver_standings(2024)` (T1API-verified when keyed, jolpica-f1/Ergast otherwise — same call either way) |
| `fastf1.get_event_schedule(2024)` | `client.event_schedule(2024)` |
| `fastf1.get_event(2024, "Monza")` | `client.event(2024, "Monza")` |

## Analysis

fastf1 mostly leaves pace/stint/comparison analysis to the user (pandas `groupby`
calls on `session.laps`). `t1f1-sdk` ships these as first-class methods, computed
locally for free or served pre-verified by `api.t1f1.com` when you have a key — same
call either way, see [Free vs Premium](../concepts/free-vs-premium.md):

```python
session.driver_pace()          # no fastf1 equivalent — was a manual groupby
session.tyre_stints()          # no fastf1 equivalent
session.compare("VER", "NOR")  # closest fastf1 equivalent: manual delta_time() + merge_asof
session.track_dominance("VER", "NOR")  # a common fastf1-community pattern, not built into fastf1 itself
```

## Caching

```python
# fastf1 — global, process-wide, mutable
import fastf1
fastf1.Cache.enable_cache("/path/to/cache")

# t1f1-sdk — scoped per Client, safer for concurrent multi-key/multi-user use
from t1f1 import Client
from t1f1.cache import enable_cache

client = Client(cache=enable_cache("/path/to/cache"))
```

See [Caching](../concepts/caching.md) for the two-tier design (raw HTTP bytes +
decoded frames) and why a warm cache skips both the network *and* re-decoding.

## pandas → polars idioms

| pandas (fastf1) | polars (t1f1-sdk) |
|---|---|
| `df[df["Compound"] == "SOFT"]` | `df.filter(pl.col("compound") == "SOFT")` |
| `df["LapTime"].dt.total_seconds()` | `df["lap_time"].dt.total_seconds()` (polars `Duration` dtype, not a pandas `Timedelta` object column) |
| `df.groupby("Driver")["LapTime"].min()` | `df.group_by("driver").agg(pl.col("lap_time").min())` |
| `df.sort_values("LapTime")` | `df.sort("lap_time")` |
| column names | `t1f1-sdk` uses `snake_case` throughout (`lap_time`, not `LapTime`) — the raw feed's `CamelCase` is normalized during decoding |

## Async

fastf1 has no async story. `t1f1-sdk`'s core is async-first (`AsyncClient`/
`AsyncSession`); `Client`/`Session` are a blocking facade over it for scripts that
don't need concurrency. If you're loading several sessions at once, the async core is
the actual "beat fastf1" lever:

```python
import asyncio
from t1f1 import AsyncClient

async def main():
    async with AsyncClient() as client:
        sessions = [client.session(2024, gp, "R") for gp in range(1, 4)]
        return await asyncio.gather(*(s.laps() for s in sessions))

results = asyncio.run(main())
```
