"""Shared test fixtures: a synthetic, fully offline F1 live-timing feed + T1API.

Everything is built in-memory. The ``.z`` streams are compressed here with the exact
raw-deflate (``wbits=-15``) + Base64 encoding the real feed uses, so the decode path is
exercised end to end without touching the network.
"""

from __future__ import annotations

import base64
import json
import zlib
from typing import Any

import pytest

# -- session coordinates used across the suite -------------------------------

YEAR = 2024
SESSION_PATH = "2024/2024-08-31_Italian_Grand_Prix/2024-08-31_Qualifying/"
F1_BASE = "https://livetiming.formula1.com/static/"
SESSION_URL = F1_BASE + SESSION_PATH
INDEX_URL = f"{F1_BASE}{YEAR}/Index.json"


# -- encoding helpers ---------------------------------------------------------


def compress_z(payload: Any) -> str:
    """Encode a payload the way the F1 feed does: JSON -> raw deflate -> Base64."""
    raw = json.dumps(payload).encode("utf-8")
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(raw) + compressor.flush()
    return base64.b64encode(compressed).decode("ascii")


def z_stream(lines: list[tuple[str, Any]]) -> str:
    """Build a ``.z.jsonStream`` document: ``HH:MM:SS.mmm"<base64>"`` per line."""
    return "\n".join(f'{ts}"{compress_z(payload)}"' for ts, payload in lines)


# -- synthetic feed payloads --------------------------------------------------


@pytest.fixture
def index_json() -> dict[str, Any]:
    return {
        "Year": YEAR,
        "Meetings": [
            {
                "Key": 1229,
                "Name": "Bahrain Grand Prix",
                "OfficialName": "FORMULA 1 BAHRAIN GRAND PRIX 2024",
                "Location": "Sakhir",
                "Sessions": [
                    {
                        "Key": 1,
                        "Type": "Qualifying",
                        "Name": "Qualifying",
                        "Path": "2024/2024-03-01_Bahrain_Grand_Prix/2024-03-01_Qualifying/",
                    }
                ],
            },
            {
                "Key": 1234,
                "Name": "Italian Grand Prix",
                "OfficialName": "FORMULA 1 PIRELLI GRAN PREMIO D'ITALIA 2024",
                "Location": "Monza",
                "Sessions": [
                    {
                        "Key": 8,
                        "Type": "Practice",
                        "Name": "Practice 1",
                        "Path": "2024/2024-08-30_Italian_Grand_Prix/2024-08-30_Practice_1/",
                    },
                    {
                        "Key": 10,
                        "Type": "Qualifying",
                        "Name": "Qualifying",
                        "Path": SESSION_PATH,
                    },
                ],
            },
        ],
    }


@pytest.fixture
def driver_list() -> dict[str, Any]:
    return {
        "1": {
            "RacingNumber": "1",
            "Tla": "VER",
            "FullName": "Max Verstappen",
            "TeamName": "Red Bull",
        },
        "4": {"RacingNumber": "4", "Tla": "NOR", "FullName": "Lando Norris", "TeamName": "McLaren"},
    }


def _car_sample(utc: str, speed_by_car: dict[str, int]) -> dict[str, Any]:
    """One CarData 'Entries' sample; channel 2 is Speed, 0 is RPM (fastf1 mapping)."""
    cars = {
        num: {"Channels": {"0": 11000, "2": speed, "3": 7, "4": 100, "5": 0, "45": 1}}
        for num, speed in speed_by_car.items()
    }
    return {"Utc": utc, "Cars": cars}


@pytest.fixture
def car_data_text() -> str:
    lines = [
        (
            "00:00:01.000",
            {"Entries": [_car_sample("2024-08-31T13:00:01.000Z", {"1": 300, "4": 290})]},
        ),
        (
            "00:00:02.000",
            {"Entries": [_car_sample("2024-08-31T13:00:02.000Z", {"1": 330, "4": 315})]},
        ),
        (
            "00:00:03.000",
            {"Entries": [_car_sample("2024-08-31T13:00:03.000Z", {"1": 355, "4": 340})]},
        ),
    ]
    return z_stream(lines)


def _pos_sample(ts: str, coords_by_car: dict[str, tuple[int, int, int]]) -> dict[str, Any]:
    entries = {
        num: {"Status": "OnTrack", "X": x, "Y": y, "Z": z}
        for num, (x, y, z) in coords_by_car.items()
    }
    return {"Timestamp": ts, "Entries": entries}


@pytest.fixture
def position_text() -> str:
    lines = [
        (
            "00:00:01.000",
            {
                "Position": [
                    _pos_sample("2024-08-31T13:00:01.000Z", {"1": (10, 20, 5), "4": (11, 21, 5)})
                ]
            },
        ),
        (
            "00:00:02.000",
            {
                "Position": [
                    _pos_sample("2024-08-31T13:00:02.000Z", {"1": (110, 60, 5), "4": (111, 61, 5)})
                ]
            },
        ),
        (
            "00:00:03.000",
            {
                "Position": [
                    _pos_sample("2024-08-31T13:00:03.000Z", {"1": (260, 90, 5), "4": (261, 91, 5)})
                ]
            },
        ),
    ]
    return z_stream(lines)


@pytest.fixture
def top_speed_payload() -> dict[str, Any]:
    """A T1API /api/v2/top-speed-telemetry-data response."""
    return {
        "session": "Q",
        "year": YEAR,
        "gp": 2,
        "drivers": [
            {"driver": "VER", "top_speed_kmh": 355.0, "lap": 12},
            {"driver": "NOR", "top_speed_kmh": 340.0, "lap": 9},
        ],
    }


@pytest.fixture
def feed(index_json, driver_list, car_data_text, position_text):
    """Bundle of the synthetic feed, keyed for convenient registration in tests."""
    return {
        INDEX_URL: json.dumps(index_json).encode("utf-8"),
        SESSION_URL + "DriverList.json": json.dumps(driver_list).encode("utf-8"),
        SESSION_URL + "CarData.z.jsonStream": car_data_text.encode("utf-8"),
        SESSION_URL + "Position.z.jsonStream": position_text.encode("utf-8"),
    }
