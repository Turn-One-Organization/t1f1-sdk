# Client API

`Client` and `AsyncClient` are the top-level entrypoints. `AsyncClient` is the real
core; `Client` is a blocking facade over it (same methods, no `await`, backed by one
persistent background event-loop thread — see
[Sync vs Async](../concepts/sync-vs-async.md)). Every example below is shown as
`Client` (sync); every method has a 1:1 `async def` equivalent on `AsyncClient`.

```python
from t1f1 import Client, AsyncClient
```

## Constructing a client

```python
Client(
    api_key: str | None = None,
    *,
    config: ClientConfig | None = None,
    cache: CacheBackend | None = None,
)
```

```python
AsyncClient(
    api_key: str | None = None,
    *,
    config: ClientConfig | None = None,
    cache: CacheBackend | None = None,
    f1_client: httpx.AsyncClient | None = None,     # inject for testing (respx/MockTransport)
    t1api_client: httpx.AsyncClient | None = None,   # inject for testing
    ergast_client: httpx.AsyncClient | None = None,  # inject for testing
)
```

| Parameter | Meaning |
|---|---|
| `api_key` | Enables the premium tier — analysis methods route to `api.t1f1.com`. Omit for free-only. |
| `config` | A `ClientConfig` overriding base URLs / timeouts / retry policy. See [Configuration](../reference/configuration.md). |
| `cache` | A `t1f1.cache.CacheBackend` (`DiskCache`/`RedisCache`, from `enable_cache()`). See [Caching](../concepts/caching.md). |

```python
from t1f1 import Client

# Free tier, no config
client = Client()

# Premium tier
client = Client(api_key="YOUR_T1API_KEY")

# With a disk cache
from t1f1.cache import enable_cache
client = Client(cache=enable_cache("./.t1f1_cache"))
```

Both classes are context managers and close their HTTP connections (and cache, if
one owns a persistent connection like Redis) on exit:

```python
with Client() as client:
    ...
```

```python
async with AsyncClient() as client:
    ...
```

Without a `with` block, call `client.close()` (sync) / `await client.aclose()`
(async) yourself when you're done.

## Properties

| Property | Type | Meaning |
|---|---|---|
| `is_premium` | `bool` | `True` if constructed with `api_key`. |
| `quota` | `QuotaInfo \| None` | T1API rate-limit usage (`limit`, `remaining`, `reset`) from the most recent premium response. `None` without a key, or before any premium request has hit the network. |
| `last_source` | `str \| None` | `"t1api"` or `"ergast"` — whichever served the most recent `driver_standings()`/`constructor_standings()` call. `None` before either has been called. |

```python
client = Client(api_key="YOUR_KEY")
print(client.is_premium)  # True

client.driver_standings(2024)
print(client.last_source)  # "t1api" (or "ergast" if T1API had an outage)
print(client.quota)        # QuotaInfo(limit=300, remaining=299, reset=1700000000) or None
```

## `session(year, gp, session) -> Session`

Build a session handle. This does **no network I/O** — resolution (looking up
`Index.json`) and fetching happen lazily the first time you call an accessor on the
returned `Session`. See the full method list on the [Session API](session.md) page.

- `year: int` — the season, e.g. `2024`.
- `gp: int | str` — round number (`1`), event key (from `Index.json`), or a fuzzy
  event name/location (`"Monza"`, `"Bahrain Grand Prix"`). **Prefer strings for
  older seasons** — see the caveat under [Events](events.md#a-note-on-round-numbers).
- `session: str` — session name or alias: `"R"`/`"Race"`, `"Q"`/`"Qualifying"`,
  `"Sprint"`, `"SQ"`/`"Sprint Qualifying"`, `"FP1"`/`"Practice 1"`, `"FP2"`, `"FP3"`.

```python
session = client.session(2024, "Monza", "Q")
session = client.session(2024, 1, "R")          # by round number
session = client.session(2024, "Bahrain Grand Prix", "FP1")
```

## Event schedule (free tier — always the F1 feed, never premium)

### `event_schedule(year: int) -> pl.DataFrame`

All events (Grand Prix weekends) for a season. Schema: `t1f1.schemas.EVENT_SCHEMA`.

```python
schedule = client.event_schedule(2024)
print(schedule.select("round", "name", "location", "start_date"))
```

### `event(year: int, gp: int | str) -> dict`

One event's row as a plain `dict` (by round number, event key, or fuzzy name).

```python
monza = client.event(2024, "Monza")
print(monza["round"], monza["official_name"])
```

### `event_sessions(year: int, gp: int | str) -> pl.DataFrame`

All sessions (FP1/FP2/FP3/Q/R/...) within one event. Schema:
`t1f1.schemas.EVENT_SESSION_SCHEMA`.

```python
sessions = client.event_sessions(2024, "Monza")
print(sessions.select("session_name", "session_type", "start_date"))
```

### `events_remaining(year: int, *, after: datetime | None = None) -> pl.DataFrame`

Events whose `end_date` is still in the future (default cutoff: `datetime.now()`).

```python
from datetime import datetime
upcoming = client.events_remaining(2024, after=datetime(2024, 7, 1))
```

## Standings & results

Prefer T1API when keyed (falls back to jolpica-f1/Ergast on a retryable upstream
error — see [Free vs Premium](../concepts/free-vs-premium.md)); always Ergast
without a key.

### `driver_standings(year: int, round: int | None = None) -> pl.DataFrame`

Schema: `t1f1.schemas.DRIVER_STANDINGS_SCHEMA`. `round=None` means end-of-season (or
current standings, for the in-progress season).

```python
standings = client.driver_standings(2024)
print(standings.select("position", "driver", "team", "points"))

# Standings as of a specific round
standings_after_10 = client.driver_standings(2024, round=10)
```

### `constructor_standings(year: int, round: int | None = None) -> pl.DataFrame`

Same shape, one row per team. Schema: `t1f1.schemas.CONSTRUCTOR_STANDINGS_SCHEMA`.

```python
teams = client.constructor_standings(2024)
```

### `race_results(year: int, round: int) -> pl.DataFrame`

Classified results for one race (always Ergast — T1API has no raw-results
endpoint). Schema: `t1f1.schemas.ERGAST_RESULTS_SCHEMA`.

```python
results = client.race_results(2024, 16)
print(results.select("position", "driver", "team", "points", "status"))
```

## Circuit info (premium only — no free-tier fallback exists)

### `circuit_info(circuit_id: int | str, *, year: int | None = None) -> CircuitInfo`

Raises `AuthError` without a key (there's no free-tier circuit geometry source at
all to fall back to). See [Circuits API](circuits.md) for the returned object's shape.

```python
client = Client(api_key="YOUR_KEY")
info = client.circuit_info("monza", year=2024)
print(info.corners)      # pl.DataFrame: number, letter, x, y, angle, distance
print(info.rotation)     # float | None
```

### `circuits(year: int) -> list[dict]`

All circuits for a season. Also premium-only.

```python
circuits = client.circuits(2024)
```

## Errors

Every method above raises subclasses of `t1f1.T1F1Error` — see
[Errors](errors.md) for the full taxonomy and how to catch them.
