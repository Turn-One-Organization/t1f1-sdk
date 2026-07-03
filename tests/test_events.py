"""events.py: season event schedule from Index.json."""

from __future__ import annotations

from datetime import datetime

import pytest
from httpx import Response

from t1f1.config import ClientConfig
from t1f1.events import get_event, get_event_schedule, get_event_sessions, get_events_remaining
from t1f1.exceptions import SessionNotFoundError
from t1f1.schemas import EVENT_SCHEMA
from t1f1.transport import AsyncTransport

YEAR = 2024
CONFIG = ClientConfig()
INDEX_URL = CONFIG.f1_url(f"{YEAR}/Index.json")

INDEX = {
    "Meetings": [
        {
            "Key": 1229,
            "Name": "Bahrain Grand Prix",
            "OfficialName": "FORMULA 1 BAHRAIN GRAND PRIX 2024",
            "Location": "Sakhir",
            "Country": {"Name": "Bahrain"},
            "Sessions": [
                {
                    "Key": 1,
                    "Type": "Qualifying",
                    "Name": "Qualifying",
                    "StartDate": "2024-03-01T18:00:00",
                    "EndDate": "2024-03-01T19:00:00",
                    "Path": "2024/x/Qualifying/",
                },
                {
                    "Key": 2,
                    "Type": "Race",
                    "Name": "Race",
                    "StartDate": "2024-03-02T18:00:00",
                    "EndDate": "2024-03-02T20:00:00",
                    "Path": "2024/x/Race/",
                },
            ],
        },
        {
            "Key": 1234,
            "Name": "Italian Grand Prix",
            "OfficialName": "FORMULA 1 PIRELLI GRAN PREMIO D'ITALIA 2024",
            "Location": "Monza",
            "Country": {"Name": "Italy"},
            "Sessions": [
                {
                    "Key": 10,
                    "Type": "Qualifying",
                    "Name": "Qualifying",
                    "StartDate": "2024-08-31T15:00:00",
                    "EndDate": "2024-08-31T16:00:00",
                    "Path": "2024/y/Qualifying/",
                }
            ],
        },
    ]
}


def _register(respx_mock):
    respx_mock.get(INDEX_URL).mock(return_value=Response(200, json=INDEX))


async def test_get_event_schedule_decodes_rounds(respx_mock):
    _register(respx_mock)
    transport = AsyncTransport(source="livetiming", config=CONFIG)
    schedule = await get_event_schedule(transport, CONFIG, YEAR)
    await transport.aclose()

    assert schedule.schema == EVENT_SCHEMA
    assert schedule.height == 2
    assert schedule["name"].to_list() == ["Bahrain Grand Prix", "Italian Grand Prix"]
    assert schedule["round"].to_list() == [1, 2]
    assert schedule["country"].to_list() == ["Bahrain", "Italy"]
    row = schedule.row(0, named=True)
    assert row["start_date"] == datetime(2024, 3, 1, 18, 0)
    assert row["end_date"] == datetime(2024, 3, 2, 20, 0)


async def test_get_event_resolves_by_fuzzy_name(respx_mock):
    _register(respx_mock)
    transport = AsyncTransport(source="livetiming", config=CONFIG)
    event = await get_event(transport, CONFIG, YEAR, "monza")
    await transport.aclose()
    assert event["name"] == "Italian Grand Prix"
    assert event["round"] == 2


async def test_get_event_sessions_lists_paths(respx_mock):
    _register(respx_mock)
    transport = AsyncTransport(source="livetiming", config=CONFIG)
    sessions = await get_event_sessions(transport, CONFIG, YEAR, 1)
    await transport.aclose()
    assert sessions.height == 2
    assert sessions["session_name"].to_list() == ["Qualifying", "Race"]
    assert sessions["path"].to_list() == ["2024/x/Qualifying/", "2024/x/Race/"]


async def test_get_events_remaining_filters_by_cutoff(respx_mock):
    _register(respx_mock)
    transport = AsyncTransport(source="livetiming", config=CONFIG)
    remaining = await get_events_remaining(transport, CONFIG, YEAR, after=datetime(2024, 6, 1))
    await transport.aclose()
    assert remaining["name"].to_list() == ["Italian Grand Prix"]


async def test_get_event_unknown_round_raises(respx_mock):
    _register(respx_mock)
    transport = AsyncTransport(source="livetiming", config=CONFIG)
    with pytest.raises(SessionNotFoundError):
        await get_event(transport, CONFIG, YEAR, 99)
    await transport.aclose()
