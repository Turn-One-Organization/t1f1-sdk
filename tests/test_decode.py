"""CarData/Position channel decoding into the canonical telemetry frame."""

from __future__ import annotations

from t1f1.ingestion.decode import (
    CAR_CHANNELS,
    build_telemetry,
    decode_car_data,
    decode_position,
)
from t1f1.schemas import TELEMETRY_SCHEMA


def _car_records():
    def sample(utc, speed, rpm):
        return {
            "Entries": [
                {
                    "Utc": utc,
                    "Cars": {
                        "1": {"Channels": {"0": rpm, "2": speed, "3": 7, "4": 100, "5": 0, "45": 1}}
                    },
                }
            ]
        }

    return [
        sample("2024-08-31T13:00:01.000Z", 300, 11000),
        sample("2024-08-31T13:00:02.000Z", 330, 11500),
        sample("2024-08-31T13:00:03.000Z", 355, 12000),
    ]


def _pos_records():
    def sample(ts, x, y):
        return {
            "Position": [
                {"Timestamp": ts, "Entries": {"1": {"X": x, "Y": y, "Z": 5, "Status": "OnTrack"}}}
            ]
        }

    return [
        sample("2024-08-31T13:00:01.000Z", 10, 20),
        sample("2024-08-31T13:00:02.000Z", 110, 60),
        sample("2024-08-31T13:00:03.000Z", 260, 90),
    ]


def test_channel_map_is_the_fastf1_mapping():
    # Guardrail against the swapped 0=Speed/2=RPM misreading in the docs.
    assert CAR_CHANNELS["0"] == "rpm"
    assert CAR_CHANNELS["2"] == "speed_kmh"


def test_decode_car_data_uses_channel_2_for_speed():
    rows = decode_car_data(_car_records(), "1")
    assert [r["speed_kmh"] for r in rows] == [300, 330, 355]
    assert [r["rpm"] for r in rows] == [11000, 11500, 12000]


def test_decode_position_extracts_xyz():
    rows = decode_position(_pos_records(), "1")
    assert rows[0]["x"] == 10 and rows[2]["y"] == 90


def test_build_telemetry_schema_and_distance():
    car_rows = decode_car_data(_car_records(), "1")
    pos_rows = decode_position(_pos_records(), "1")
    frame = build_telemetry(car_rows, pos_rows, driver="VER", driver_number="1")

    assert frame.schema == TELEMETRY_SCHEMA
    assert frame.height == 3
    assert frame["driver"].unique().to_list() == ["VER"]

    # Speed sane; gear within range.
    assert 300 <= frame["speed_kmh"].max() <= 360
    assert frame["gear"].min() >= 0 and frame["gear"].max() <= 8

    # Distance is monotonic non-decreasing and starts at zero.
    distance = frame["distance"].to_list()
    assert distance[0] == 0.0
    assert all(b >= a for a, b in zip(distance, distance[1:], strict=False))

    # Position merged in.
    assert frame["x"].null_count() == 0


def test_build_telemetry_empty_input_returns_empty_schema():
    frame = build_telemetry([], [], driver="VER", driver_number="1")
    assert frame.is_empty()
    assert frame.schema == TELEMETRY_SCHEMA
