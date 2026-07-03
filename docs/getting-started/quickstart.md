# Quickstart

This is the shortest path to a working session query.

## Blocking client

```python
from t1f1 import Client

with Client() as client:
    session = client.session(2024, "Monza", "Q")
    telemetry = session.telemetry("VER")
    print(telemetry.head())
```

## Async client

```python
import asyncio

from t1f1 import AsyncClient


async def main() -> None:
    async with AsyncClient() as client:
        session = client.session(2024, "Monza", "Q")
        telemetry = await session.telemetry("VER")
        print(telemetry.head())


asyncio.run(main())
```

## What you get back

Most methods return `polars.DataFrame` objects. Session access is lazy, so data is fetched when
you call a method, not when you create the session handle.

## A more complete example

```python
from t1f1 import Client

with Client() as client:
    session = client.session(2024, "Monza", "Q")

    # Raw data
    telemetry = session.telemetry("VER")
    laps = session.laps().pick_drivers("VER").pick_quicklaps()
    results = session.results()

    # Derived analysis — free tier computes locally, premium uses api.t1f1.com if keyed
    pace = session.driver_pace()
    stints = session.tyre_stints()
    comparison = session.compare("VER", "NOR")

    # Season-level lookups (no session() needed)
    standings = client.driver_standings(2024)
    schedule = client.event_schedule(2024)
```

## Next step

Read the [Client API](../api-reference/client.md) and [Session API](../api-reference/session.md)
for the full method-by-method reference with examples, or
[Schemas](../api-reference/schemas.md) for exact column names/types on every
returned frame.