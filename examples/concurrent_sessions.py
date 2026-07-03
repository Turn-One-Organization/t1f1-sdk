"""Async core: load several sessions concurrently over one shared connection pool.

This is the "beat fastf1" lever for anything working across multiple
sessions/events — fastf1's sync, sequential requests can't do this.
"""

import asyncio

from t1f1 import AsyncClient


async def main() -> None:
    async with AsyncClient() as client:
        sessions = [client.session(2024, gp, "R") for gp in range(1, 4)]
        results = await asyncio.gather(*(s.laps() for s in sessions))
    for session, laps in zip(sessions, results, strict=True):
        print(session.gp, laps.to_polars().height, "laps")


if __name__ == "__main__":
    asyncio.run(main())
