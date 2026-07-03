# Events API

Event/schedule lookups, available on `Client`/`AsyncClient` directly (no `session()`
needed). Free tier only, deliberately — see the note at the bottom of this page.

```python
from t1f1 import Client
client = Client()
```

## `event_schedule(year: int) -> pl.DataFrame`

Every event (Grand Prix weekend) for a season. Schema:
`round, event_key, name, official_name, location, country, start_date, end_date`
(`t1f1.schemas.EVENT_SCHEMA`).

```python
schedule = client.event_schedule(2024)
print(schedule.select("round", "name", "location", "start_date"))
```

## `event(year: int, gp: int | str) -> dict`

One event's row as a plain `dict`, resolved by round number, event key, or fuzzy
name/location match.

```python
monza = client.event(2024, "Monza")
print(monza)
# {"round": 16, "event_key": "1234", "name": "Italian Grand Prix", ...}

bahrain = client.event(2024, "Bahrain Grand Prix")  # fuzzy name match
first_round = client.event(2024, 1)                 # by round number
```

## `event_sessions(year: int, gp: int | str) -> pl.DataFrame`

Every session (FP1/FP2/FP3/Q/Sprint/R) within one event, with its live-timing feed
path. Schema: `round, session_name, session_type, start_date, path`
(`t1f1.schemas.EVENT_SESSION_SCHEMA`).

```python
sessions = client.event_sessions(2024, "Monza")
print(sessions.select("session_name", "session_type", "start_date"))
```

## `events_remaining(year: int, *, after: datetime | None = None) -> pl.DataFrame`

Events whose `end_date` is still in the future relative to `after` (default:
`datetime.now()`). Same schema as `event_schedule`.

```python
from datetime import datetime
upcoming = client.events_remaining(2024, after=datetime(2024, 7, 1))
print(upcoming.select("round", "name", "start_date"))
```

## A note on round numbers

**Known, confirmed-live limitation:** a past season's `Index.json` (the free feed's
calendar source) does not necessarily list every round. Checked live against 2024:
its `Index.json` currently only retains the final 15 of 24 meetings (starting from
the Spanish GP — Bahrain through Monaco are entirely absent, with no error or
warning).

Since an integer `gp` (round number) resolves **positionally** into whatever
`Meetings` the index actually contains — not the real FIA round number — this means
`client.session(2024, 1, "Q")` can silently resolve to the wrong Grand Prix on an
affected season. There's no cheap way to detect an incomplete index from the free
feed alone.

**Prefer event name or event key** (`gp="Bahrain Grand Prix"`, not `gp=1`) for older
or partial seasons, especially when correctness matters more than convenience.

```python
# Fragile for older seasons if the index has gaps:
session = client.session(2024, 1, "Q")

# Robust regardless of index gaps:
session = client.session(2024, "Bahrain Grand Prix", "Q")
```

## Why free tier only

T1API's `/api/v2/seasons/{year}/events` proxies the same `Index.json` source but
drops session start/end dates (per its own docs) — routing there would be strictly
*worse* than reconstructing from `Index.json` directly, so `events.py` has no
premium path at all, unlike most other analysis methods.
