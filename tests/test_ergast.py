"""ergast.py: jolpica-f1 (Ergast-compatible) standings/results parsing."""

from __future__ import annotations

import pytest
from httpx import Response

from t1f1.config import ClientConfig
from t1f1.ergast import constructor_standings, driver_standings, race_results
from t1f1.schemas import (
    CONSTRUCTOR_STANDINGS_SCHEMA,
    DRIVER_STANDINGS_SCHEMA,
    ERGAST_RESULTS_SCHEMA,
)
from t1f1.transport import AsyncTransport

CONFIG = ClientConfig()
BASE = CONFIG.ergast_base_url


def _driver_standings_payload():
    return {
        "MRData": {
            "StandingsTable": {
                "StandingsLists": [
                    {
                        "season": "2024",
                        "DriverStandings": [
                            {
                                "position": "1",
                                "points": "437",
                                "wins": "9",
                                "Driver": {
                                    "driverId": "max_verstappen",
                                    "code": "VER",
                                    "givenName": "Max",
                                    "familyName": "Verstappen",
                                    "nationality": "Dutch",
                                },
                                "Constructors": [
                                    {"constructorId": "red_bull", "name": "Red Bull Racing"}
                                ],
                            },
                            {
                                "position": "2",
                                "points": "374",
                                "wins": "3",
                                "Driver": {
                                    "driverId": "norris",
                                    "code": "NOR",
                                    "givenName": "Lando",
                                    "familyName": "Norris",
                                    "nationality": "British",
                                },
                                "Constructors": [{"constructorId": "mclaren", "name": "McLaren"}],
                            },
                        ],
                    }
                ]
            }
        }
    }


def _constructor_standings_payload():
    return {
        "MRData": {
            "StandingsTable": {
                "StandingsLists": [
                    {
                        "ConstructorStandings": [
                            {
                                "position": "1",
                                "points": "666",
                                "wins": "9",
                                "Constructor": {
                                    "constructorId": "mclaren",
                                    "name": "McLaren",
                                    "nationality": "British",
                                },
                            }
                        ]
                    }
                ]
            }
        }
    }


def _race_results_payload():
    return {
        "MRData": {
            "RaceTable": {
                "Races": [
                    {
                        "Results": [
                            {
                                "position": "1",
                                "grid": "4",
                                "laps": "53",
                                "status": "Finished",
                                "points": "25",
                                "Driver": {"driverId": "leclerc", "code": "LEC"},
                                "Constructor": {"name": "Ferrari"},
                                "Time": {"time": "1:14:31.415"},
                                "FastestLap": {"rank": "3", "Time": {"time": "1:23.032"}},
                            }
                        ]
                    }
                ]
            }
        }
    }


async def test_driver_standings_parses_correctly(respx_mock):
    respx_mock.get(BASE + "2024/driverStandings.json").mock(
        return_value=Response(200, json=_driver_standings_payload())
    )
    transport = AsyncTransport(source="ergast", config=CONFIG)
    result = await driver_standings(transport, CONFIG, 2024)
    await transport.aclose()

    assert result.schema == DRIVER_STANDINGS_SCHEMA
    assert result["driver"].to_list() == ["VER", "NOR"]
    assert result["full_name"].to_list() == ["Max Verstappen", "Lando Norris"]
    assert result["points"].to_list() == pytest.approx([437.0, 374.0])
    assert result["team"].to_list() == ["Red Bull Racing", "McLaren"]


async def test_driver_standings_with_round_hits_round_scoped_url(respx_mock):
    route = respx_mock.get(BASE + "2024/5/driverStandings.json").mock(
        return_value=Response(200, json=_driver_standings_payload())
    )
    transport = AsyncTransport(source="ergast", config=CONFIG)
    await driver_standings(transport, CONFIG, 2024, round=5)
    await transport.aclose()
    assert route.called


async def test_constructor_standings_parses_correctly(respx_mock):
    respx_mock.get(BASE + "2024/constructorStandings.json").mock(
        return_value=Response(200, json=_constructor_standings_payload())
    )
    transport = AsyncTransport(source="ergast", config=CONFIG)
    result = await constructor_standings(transport, CONFIG, 2024)
    await transport.aclose()

    assert result.schema == CONSTRUCTOR_STANDINGS_SCHEMA
    assert result["team"].to_list() == ["McLaren"]
    assert result["points"].to_list() == pytest.approx([666.0])


async def test_race_results_parses_correctly(respx_mock):
    respx_mock.get(BASE + "2024/16/results.json").mock(
        return_value=Response(200, json=_race_results_payload())
    )
    transport = AsyncTransport(source="ergast", config=CONFIG)
    result = await race_results(transport, CONFIG, 2024, 16)
    await transport.aclose()

    assert result.schema == ERGAST_RESULTS_SCHEMA
    assert result["driver"].to_list() == ["LEC"]
    assert result["time"].to_list() == ["1:14:31.415"]
    assert result["fastest_lap_time"].to_list() == ["1:23.032"]


async def test_driver_standings_empty_returns_empty_schema(respx_mock):
    respx_mock.get(BASE + "2024/driverStandings.json").mock(
        return_value=Response(200, json={"MRData": {"StandingsTable": {"StandingsLists": []}}})
    )
    transport = AsyncTransport(source="ergast", config=CONFIG)
    result = await driver_standings(transport, CONFIG, 2024)
    await transport.aclose()
    assert result.is_empty()
    assert result.schema == DRIVER_STANDINGS_SCHEMA
