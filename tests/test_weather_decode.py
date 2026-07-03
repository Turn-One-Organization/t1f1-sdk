"""WeatherData.jsonStream decoding."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from t1f1.ingestion.session_clock import SessionClock
from t1f1.ingestion.stream import TIMESTAMP_KEY
from t1f1.ingestion.weather import decode_weather
from t1f1.schemas import WEATHER_SCHEMA


def test_decode_weather_casts_numeric_and_boolean_fields():
    records = [
        {
            TIMESTAMP_KEY: "00:00:00.000",
            "AirTemp": "24.5",
            "TrackTemp": "35.0",
            "Humidity": "45.0",
            "Pressure": "1013.0",
            "Rainfall": "0",
            "WindDirection": "180",
            "WindSpeed": "1.5",
        },
        {
            TIMESTAMP_KEY: "00:01:00.000",
            "AirTemp": "24.7",
            "TrackTemp": "35.5",
            "Humidity": "44.0",
            "Pressure": "1013.2",
            "Rainfall": "1",
            "WindDirection": "185",
            "WindSpeed": "1.8",
        },
    ]

    clock = SessionClock(datetime(2024, 8, 31, 13, 0, tzinfo=timezone.utc))
    frame = decode_weather(records, clock=clock)

    assert frame.schema == WEATHER_SCHEMA
    assert frame.height == 2
    assert frame["air_temp"].to_list() == pytest.approx([24.5, 24.7])
    assert frame["rainfall"].to_list() == [False, True]
    assert frame["timestamp"].null_count() == 0


def test_decode_weather_without_clock_leaves_timestamp_null():
    records = [{TIMESTAMP_KEY: "00:00:00.000", "AirTemp": "24.5"}]
    frame = decode_weather(records)
    assert frame["timestamp"].to_list() == [None]


def test_decode_weather_empty_input_returns_empty_schema():
    frame = decode_weather([])
    assert frame.is_empty()
    assert frame.schema == WEATHER_SCHEMA
