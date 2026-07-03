"""Standings and race results via jolpica-f1 (Ergast-compatible, free, no key needed).

Hits jolpica-f1's public REST API directly, parsing the classic ergast.com response
envelope (``MRData.StandingsTable`` / ``.RaceTable``) that jolpica-f1 deliberately
stays compatible with. When a T1API key is present, ``AsyncClient`` prefers T1API's
``/api/v2/seasons/*`` standings endpoints instead (mixed livetiming+ergast sourced,
per T1API's own docs) and falls back to this module if that call fails.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from t1f1.config import ClientConfig
from t1f1.schemas import (
    CONSTRUCTOR_STANDINGS_SCHEMA,
    DRIVER_STANDINGS_SCHEMA,
    ERGAST_RESULTS_SCHEMA,
    empty_constructor_standings,
    empty_driver_standings,
    empty_ergast_results,
)
from t1f1.transport import AsyncTransport


def _standings_list(payload: Any) -> dict[str, Any]:
    table = payload.get("MRData", {}).get("StandingsTable", {}) if isinstance(payload, dict) else {}
    lists = table.get("StandingsLists", [])
    return lists[0] if lists else {}


async def driver_standings(
    transport: AsyncTransport,
    config: ClientConfig,
    year: int,
    round: int | None = None,  # noqa: A002 (matches Ergast/fastf1's own parameter name)
) -> pl.DataFrame:
    """Driver championship standings for ``year`` (end of season, or after ``round``)."""
    path = (
        f"{year}/driverStandings.json" if round is None else f"{year}/{round}/driverStandings.json"
    )
    payload = await transport.get_json(config.ergast_url(path))
    entries = _standings_list(payload).get("DriverStandings", [])
    rows: list[dict[str, Any]] = []
    for entry in entries:
        driver = entry.get("Driver", {})
        constructors = entry.get("Constructors", [])
        team = constructors[-1].get("name") if constructors else None
        full_name = f"{driver.get('givenName', '')} {driver.get('familyName', '')}".strip()
        rows.append(
            {
                "position": entry.get("position"),
                "driver": driver.get("code"),
                "driver_id": driver.get("driverId"),
                "full_name": full_name,
                "team": team,
                "nationality": driver.get("nationality"),
                "points": entry.get("points"),
                "wins": entry.get("wins"),
            }
        )
    if not rows:
        return empty_driver_standings()
    return pl.DataFrame(rows, schema=DRIVER_STANDINGS_SCHEMA)


async def constructor_standings(
    transport: AsyncTransport,
    config: ClientConfig,
    year: int,
    round: int | None = None,  # noqa: A002
) -> pl.DataFrame:
    """Constructor championship standings for ``year`` (end of season, or after ``round``)."""
    path = (
        f"{year}/constructorStandings.json"
        if round is None
        else f"{year}/{round}/constructorStandings.json"
    )
    payload = await transport.get_json(config.ergast_url(path))
    entries = _standings_list(payload).get("ConstructorStandings", [])
    rows: list[dict[str, Any]] = []
    for entry in entries:
        constructor = entry.get("Constructor", {})
        rows.append(
            {
                "position": entry.get("position"),
                "team": constructor.get("name"),
                "team_id": constructor.get("constructorId"),
                "nationality": constructor.get("nationality"),
                "points": entry.get("points"),
                "wins": entry.get("wins"),
            }
        )
    if not rows:
        return empty_constructor_standings()
    return pl.DataFrame(rows, schema=CONSTRUCTOR_STANDINGS_SCHEMA)


async def race_results(
    transport: AsyncTransport, config: ClientConfig, year: int, round: int  # noqa: A002
) -> pl.DataFrame:
    """Classified results for one race."""
    payload = await transport.get_json(config.ergast_url(f"{year}/{round}/results.json"))
    table = payload.get("MRData", {}).get("RaceTable", {}) if isinstance(payload, dict) else {}
    races = table.get("Races", [])
    entries = races[0].get("Results", []) if races else []
    rows: list[dict[str, Any]] = []
    for entry in entries:
        driver = entry.get("Driver", {})
        constructor = entry.get("Constructor", {})
        fastest_lap = entry.get("FastestLap", {})
        rows.append(
            {
                "position": entry.get("position"),
                "driver": driver.get("code"),
                "driver_id": driver.get("driverId"),
                "team": constructor.get("name"),
                "grid": entry.get("grid"),
                "laps": entry.get("laps"),
                "status": entry.get("status"),
                "points": entry.get("points"),
                "time": (entry.get("Time") or {}).get("time"),
                "fastest_lap_rank": fastest_lap.get("rank"),
                "fastest_lap_time": (fastest_lap.get("Time") or {}).get("time"),
            }
        )
    if not rows:
        return empty_ergast_results()
    return pl.DataFrame(rows, schema=ERGAST_RESULTS_SCHEMA)
