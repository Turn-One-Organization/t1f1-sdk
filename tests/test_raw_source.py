"""Free-tier RawF1Source end to end against the synthetic feed."""

from __future__ import annotations

import polars as pl
import pytest
from httpx import Response

from t1f1 import AsyncClient
from t1f1.exceptions import SessionNotFoundError
from t1f1.schemas import LAP_SCHEMA, RESULTS_SCHEMA, TELEMETRY_SCHEMA

from .conftest import INDEX_URL, YEAR


def _register(respx_mock, feed):
    """Register every feed URL and return ``{filename: route}`` for call assertions."""
    routes = {}
    for url, content in feed.items():
        route = respx_mock.get(url).mock(return_value=Response(200, content=content))
        routes[url.rsplit("/", 1)[-1]] = route
    return routes


async def test_telemetry_returns_canonical_frame(respx_mock, feed):
    _register(respx_mock, feed)
    async with AsyncClient() as client:
        tel = await client.session(YEAR, 2, "Q").telemetry("VER")
    assert tel.schema == TELEMETRY_SCHEMA
    assert tel.height == 3
    assert tel["speed_kmh"].max() == pytest.approx(355.0)
    assert tel["driver"].unique().to_list() == ["VER"]


async def test_telemetry_accepts_racing_number(respx_mock, feed):
    _register(respx_mock, feed)
    async with AsyncClient() as client:
        tel = await client.session(YEAR, 2, "Q").telemetry("4")
    assert tel["driver_number"].unique().to_list() == ["4"]
    assert tel["speed_kmh"].max() == pytest.approx(340.0)


async def test_top_speeds_computed_locally(respx_mock, feed):
    _register(respx_mock, feed)
    async with AsyncClient() as client:
        result = await client.session(YEAR, 2, "Q").top_speeds()
    assert result["driver"].to_list() == ["VER", "NOR"]
    assert result["top_speed_kmh"].to_list() == pytest.approx([355.0, 340.0])


async def test_unknown_session_raises(respx_mock, index_json):
    respx_mock.get(INDEX_URL).mock(return_value=Response(200, json=index_json))
    async with AsyncClient() as client:
        with pytest.raises(SessionNotFoundError):
            await client.session(YEAR, 2, "sprint").telemetry("VER")


async def test_laps_reconstructs_both_drivers_with_stints_and_pit(respx_mock, feed):
    _register(respx_mock, feed)
    async with AsyncClient() as client:
        laps = await client.session(YEAR, 2, "Q")._raw.laps()

    assert laps.schema == LAP_SCHEMA
    assert laps.height == 4
    ver = laps.filter(laps["driver"] == "VER").sort("lap_number")
    ver_lap_seconds = [t.total_seconds() for t in ver["lap_time"].to_list()]
    assert ver_lap_seconds == pytest.approx([80.287, 82.0])
    assert ver["compound"].to_list() == ["SOFT", "HARD"]
    # VER pits between lap 1 and lap 2; NOR never does.
    assert ver.row(1, named=True)["pit_in_time"] is not None
    nor = laps.filter(laps["driver"] == "NOR").sort("lap_number")
    assert nor["pit_in_time"].null_count() == 2


async def test_results_qualifying_includes_grid_and_q1(respx_mock, feed):
    _register(respx_mock, feed)
    async with AsyncClient() as client:
        results = await client.session(YEAR, 2, "Q")._raw.results()

    assert results.schema == RESULTS_SCHEMA
    assert results["driver"].to_list() == ["VER", "NOR"]
    assert results["grid_position"].to_list() == [1, 3]
    assert results["q1"].null_count() == 0


async def test_weather_and_messages_streams(respx_mock, feed):
    _register(respx_mock, feed)
    async with AsyncClient() as client:
        source = client.session(YEAR, 2, "Q")._raw
        weather = await source.weather()
        track_status = await source.track_status()
        session_status = await source.session_status()
        race_control = await source.race_control_messages()
        total_laps = await source.total_laps()

    assert weather.height == 2
    assert weather["air_temp"].to_list() == pytest.approx([24.5, 24.7])
    assert track_status["status"].to_list() == ["1", "2", "1"]
    assert session_status["status"].to_list() == ["Started", "Finished"]
    assert race_control.height == 1
    assert race_control.row(0, named=True)["flag"] == "YELLOW"
    assert total_laps == 2


async def test_load_prefetches_only_requested_streams(respx_mock, feed):
    calls = _register(respx_mock, feed)
    async with AsyncClient() as client:
        source = client.session(YEAR, 2, "Q")._raw
        await source.load(laps=True, telemetry=False, weather=False, messages=False)

    assert calls["TimingData.jsonStream"].called
    assert not calls["CarData.z.jsonStream"].called
    assert not calls["WeatherData.jsonStream"].called
    assert not calls["TrackStatus.jsonStream"].called


async def test_speed_trap_top_speeds(respx_mock, feed):
    _register(respx_mock, feed)
    async with AsyncClient() as client:
        result = await client.session(YEAR, 2, "Q")._raw.speed_trap_top_speeds()
    assert result["driver"].to_list() == ["VER", "NOR"]
    assert result["top_speed_kmh"].to_list() == pytest.approx([330.0, 319.0])
    assert result.filter(pl.col("driver") == "VER")["lap_number"].to_list() == [1]


async def test_driver_pace_excludes_vers_box_lap(respx_mock, feed):
    _register(respx_mock, feed)
    async with AsyncClient() as client:
        result = await client.session(YEAR, 2, "Q")._raw.driver_pace()
    by_driver = {row["driver"]: row["laps"] for row in result.iter_rows(named=True)}
    # VER's lap 2 immediately follows a pit stop, so pick_wo_box() drops it.
    assert by_driver["VER"] == 1
    assert by_driver["NOR"] == 2


async def test_tyre_stints_reflects_ver_compound_change(respx_mock, feed):
    _register(respx_mock, feed)
    async with AsyncClient() as client:
        result = await client.session(YEAR, 2, "Q")._raw.tyre_stints()
    ver = result.filter(pl.col("driver") == "VER").sort("stint")
    assert ver["compound"].to_list() == ["SOFT", "HARD"]
    nor = result.filter(pl.col("driver") == "NOR")
    assert nor["compound"].to_list() == ["MEDIUM"]
    assert nor.row(0, named=True)["lap_count"] == 2


async def test_qualifying_results_gap_to_pole(respx_mock, feed):
    _register(respx_mock, feed)
    async with AsyncClient() as client:
        result = await client.session(YEAR, 2, "Q")._raw.qualifying_results()
    assert result["driver"].to_list() == ["VER", "NOR"]
    gaps = [g.total_seconds() if g is not None else None for g in result["gap_to_pole"].to_list()]
    assert gaps[0] == pytest.approx(0.0)
    assert gaps[1] == pytest.approx(0.614, abs=1e-3)
