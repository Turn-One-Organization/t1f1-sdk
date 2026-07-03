"""RawF1Source.lap_telemetry / driver_ahead: wiring over an aligned mini feed.

Uses its own CarData/TimingData fixtures (rather than the shared ``feed`` fixture)
because these need a CarData time range that actually overlaps the TimingData-derived
lap windows, which the shared fixtures weren't built to guarantee.
"""

from __future__ import annotations

import json

import pytest
from httpx import Response

from t1f1 import AsyncClient

from .conftest import INDEX_URL, SESSION_PATH, SESSION_URL, YEAR, plain_stream, z_stream

SESSION_INFO = {
    "Meeting": {"Name": "Italian Grand Prix"},
    "Type": "Qualifying",
    "Name": "Qualifying",
    "StartDate": "2024-08-31T15:00:00",
    "GmtOffset": "02:00:00",
}


def _car_sample(second: int, speed_by_car: dict[str, int]) -> dict:
    utc = f"2024-08-31T13:00:{second:02d}.000Z"
    cars = {
        num: {"Channels": {"0": 11000, "2": speed, "3": 7, "4": 100, "5": 0, "45": 0}}
        for num, speed in speed_by_car.items()
    }
    return {"Utc": utc, "Cars": cars}


def _pos_sample(second: int, coords_by_car: dict[str, tuple[int, int, int]]) -> dict:
    ts = f"2024-08-31T13:00:{second:02d}.000Z"
    entries = {
        num: {"Status": "OnTrack", "X": x, "Y": y, "Z": z}
        for num, (x, y, z) in coords_by_car.items()
    }
    return {"Timestamp": ts, "Entries": entries}


def _build_feed() -> dict[str, bytes]:
    # VER ("1") and NOR ("4") both run steady speed for 11 seconds (13:00:00-13:00:10).
    car_lines = [
        (f"00:00:{s:02d}.000", {"Entries": [_car_sample(s, {"1": 300 + s, "4": 280 + s})]})
        for s in range(11)
    ]
    pos_lines = [
        (
            f"00:00:{s:02d}.000",
            {"Position": [_pos_sample(s, {"1": (s * 10, 0, 0), "4": (s * 10 - 50, 0, 0)})]},
        )
        for s in range(11)
    ]

    index_json = {
        "Meetings": [
            {
                "Key": 1234,
                "Name": "Italian Grand Prix",
                "OfficialName": "Italian Grand Prix",
                "Location": "Monza",
                "Sessions": [
                    {"Key": 10, "Type": "Qualifying", "Name": "Qualifying", "Path": SESSION_PATH}
                ],
            }
        ]
    }
    driver_list = {
        "1": {
            "RacingNumber": "1",
            "Tla": "VER",
            "FullName": "Max Verstappen",
            "TeamName": "Red Bull",
        },
        "4": {"RacingNumber": "4", "Tla": "NOR", "FullName": "Lando Norris", "TeamName": "McLaren"},
    }
    # A lead-in record anchors the session start at elapsed 0s (like the real feed's
    # grid-position announcements before the first completed lap). VER: lap 1
    # completes at elapsed 5s, lap 2 completes at elapsed 10s.
    timing_lines = [
        ("00:00:00.000", {"Lines": {"1": {"Line": 1}}}),
        (
            "00:00:05.000",
            {"Lines": {"1": {"Position": "1", "LastLapTime": {"Value": "5.000"}}}},
        ),
        (
            "00:00:10.000",
            {"Lines": {"1": {"Position": "1", "LastLapTime": {"Value": "5.000"}}}},
        ),
    ]

    return {
        INDEX_URL: json.dumps(index_json).encode("utf-8"),
        SESSION_URL + "DriverList.json": json.dumps(driver_list).encode("utf-8"),
        SESSION_URL + "SessionInfo.json": json.dumps(SESSION_INFO).encode("utf-8"),
        SESSION_URL + "CarData.z.jsonStream": z_stream(car_lines).encode("utf-8"),
        SESSION_URL + "Position.z.jsonStream": z_stream(pos_lines).encode("utf-8"),
        SESSION_URL + "TimingData.jsonStream": plain_stream(timing_lines).encode("utf-8"),
        SESSION_URL + "TimingAppData.jsonStream": plain_stream([]).encode("utf-8"),
        SESSION_URL + "TrackStatus.jsonStream": plain_stream([]).encode("utf-8"),
        SESSION_URL + "SessionStatus.jsonStream": plain_stream([]).encode("utf-8"),
        SESSION_URL + "RaceControlMessages.jsonStream": plain_stream([]).encode("utf-8"),
        SESSION_URL + "LapCount.jsonStream": plain_stream([]).encode("utf-8"),
    }


def _register(respx_mock, feed):
    for url, content in feed.items():
        respx_mock.get(url).mock(return_value=Response(200, content=content))


async def test_lap_telemetry_slices_to_the_lap_window(respx_mock):
    _register(respx_mock, _build_feed())
    async with AsyncClient() as client:
        session = client.session(YEAR, 1, "Q")
        lap1 = await session.lap_telemetry("VER", 1)
        lap2 = await session.lap_telemetry("VER", 2)

    # lap 1: samples with 0s <= t < 5s -> 5 samples (00,01,02,03,04).
    assert lap1.height == 5
    assert lap1["timestamp"].max().second == 4
    # lap 2: samples with 5s <= t < 10s (open-ended since it's the last lap here
    # from the *feed's* perspective) -> 00:00:05 through 00:00:10 inclusive.
    assert lap2.height == 6
    assert lap2["timestamp"].min().second == 5

    # distance/relative_distance are recomputed lap-relative (start at/near 0).
    assert lap1["distance"][0] == pytest.approx(0.0)
    assert lap2["distance"][0] == pytest.approx(0.0)
    assert lap1["relative_distance"].max() == pytest.approx(1.0)


async def test_lap_telemetry_unknown_lap_returns_empty(respx_mock):
    _register(respx_mock, _build_feed())
    async with AsyncClient() as client:
        session = client.session(YEAR, 1, "Q")
        tel = await session.lap_telemetry("VER", 99)
    assert tel.is_empty()


async def test_driver_ahead_reports_nearest_positive_gap(respx_mock):
    _register(respx_mock, _build_feed())
    async with AsyncClient() as client:
        session = client.session(YEAR, 1, "Q")
        tel = await session.driver_ahead("VER")

    assert "driver_ahead" in tel.columns
    assert "distance_to_driver_ahead" in tel.columns
    assert tel.height == 11
