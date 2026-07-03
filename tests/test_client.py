"""Client wiring: dual-tier routing and sync/async parity."""

from __future__ import annotations

import pytest
from httpx import Response

from t1f1 import AsyncClient, Client
from t1f1.cache import DiskCache
from t1f1.exceptions import AuthError

from .conftest import INDEX_URL, SESSION_URL, YEAR

TOP_SPEED_ROUTE = r".*/api/v2/top-speed-telemetry-data.*"
T1API_DRIVER_STANDINGS_ROUTE = r".*/api/v2/seasons/2024/drivers-standings.*"
ERGAST_DRIVER_STANDINGS_URL = "https://api.jolpi.ca/ergast/f1/2024/driverStandings.json"


def _register_feed(respx_mock, feed):
    routes = {}
    for url, content in feed.items():
        routes[url] = respx_mock.get(url).mock(return_value=Response(200, content=content))
    return routes


async def test_free_tier_computes_analysis_locally(respx_mock, feed):
    _register_feed(respx_mock, feed)
    api = respx_mock.get(url__regex=TOP_SPEED_ROUTE).mock(return_value=Response(200, json={}))
    async with AsyncClient() as client:
        assert not client.is_premium
        result = await client.session(YEAR, 2, "Q").top_speeds()
    assert not api.called
    assert result["driver"].to_list() == ["VER", "NOR"]


async def test_premium_tier_prefers_api(respx_mock, feed, top_speed_payload):
    _register_feed(respx_mock, feed)
    api = respx_mock.get(url__regex=TOP_SPEED_ROUTE).mock(
        return_value=Response(200, json=top_speed_payload)
    )
    async with AsyncClient(api_key="key") as client:
        assert client.is_premium
        await client.session(YEAR, 2, "Q").top_speeds()
    assert api.called


def test_sync_client_parity(respx_mock, feed):
    _register_feed(respx_mock, feed)
    with Client() as client:
        tel = client.session(YEAR, 2, "Q").telemetry("VER")
        top = client.session(YEAR, 2, "Q").top_speeds()
    assert tel.height == 3
    assert tel["speed_kmh"].max() == pytest.approx(355.0)
    assert top["driver"].to_list() == ["VER", "NOR"]


def test_sync_session_load_then_laps_and_results(respx_mock, feed):
    from t1f1.frames.laps import LapsFrame

    _register_feed(respx_mock, feed)
    with Client() as client:
        session = client.session(YEAR, 2, "Q").load(telemetry=False)
        laps = session.laps()
        results = session.results()

    assert isinstance(laps, LapsFrame)
    assert laps.pick_drivers("VER").to_polars().height == 2
    assert results["driver"].to_list() == ["VER", "NOR"]


async def test_async_session_weather_and_messages_always_raw(respx_mock, feed):
    _register_feed(respx_mock, feed)
    async with AsyncClient(api_key="secret") as client:
        session = client.session(YEAR, 2, "Q")
        weather = await session.weather()
        total_laps = await session.total_laps()

    assert weather.height == 2
    assert total_laps == 2


async def test_driver_standings_prefers_t1api_when_keyed(respx_mock):
    payload = {
        "year": 2024,
        "round": None,
        "source": "livetiming",
        "standings": [
            {
                "position": 1,
                "points": 437.0,
                "wins": 9,
                "driver_code": "VER",
                "driver_name": "Max Verstappen",
                "team": "Red Bull Racing",
                "nationality": "NED",
            }
        ],
    }
    t1api = respx_mock.get(url__regex=T1API_DRIVER_STANDINGS_ROUTE).mock(
        return_value=Response(200, json=payload)
    )
    ergast = respx_mock.get(ERGAST_DRIVER_STANDINGS_URL).mock(return_value=Response(200, json={}))
    async with AsyncClient(api_key="secret") as client:
        result = await client.driver_standings(2024)
    assert t1api.called
    assert not ergast.called
    assert result["driver"].to_list() == ["VER"]
    assert result["full_name"].to_list() == ["Max Verstappen"]


async def test_driver_standings_falls_back_to_ergast_without_key(respx_mock):
    ergast_payload = {
        "MRData": {
            "StandingsTable": {
                "StandingsLists": [
                    {
                        "DriverStandings": [
                            {
                                "position": "1",
                                "points": "437",
                                "wins": "9",
                                "Driver": {
                                    "code": "VER",
                                    "driverId": "max_verstappen",
                                    "givenName": "Max",
                                    "familyName": "Verstappen",
                                    "nationality": "Dutch",
                                },
                                "Constructors": [{"name": "Red Bull Racing"}],
                            }
                        ]
                    }
                ]
            }
        }
    }
    t1api = respx_mock.get(url__regex=T1API_DRIVER_STANDINGS_ROUTE).mock(
        return_value=Response(200, json={})
    )
    respx_mock.get(ERGAST_DRIVER_STANDINGS_URL).mock(
        return_value=Response(200, json=ergast_payload)
    )
    async with AsyncClient() as client:
        assert not client.is_premium
        result = await client.driver_standings(2024)
    assert not t1api.called
    assert result["driver"].to_list() == ["VER"]


async def test_circuit_info_requires_premium():
    async with AsyncClient() as client:
        with pytest.raises(AuthError):
            await client.circuit_info(1)


async def test_driver_pace_prefers_premium_when_keyed(respx_mock, feed):
    _register_feed(respx_mock, feed)
    api = respx_mock.get(url__regex=r".*/api/v2/driver-pace-data.*").mock(
        return_value=Response(200, json={"drivers": []})
    )
    async with AsyncClient(api_key="secret") as client:
        await client.session(YEAR, 2, "Q").driver_pace()
    assert api.called


async def test_driver_pace_computed_locally_without_key(respx_mock, feed):
    _register_feed(respx_mock, feed)
    api = respx_mock.get(url__regex=r".*/api/v2/driver-pace-data.*").mock(
        return_value=Response(200, json={"drivers": []})
    )
    async with AsyncClient() as client:
        result = await client.session(YEAR, 2, "Q").driver_pace()
    assert not api.called
    assert set(result["driver"].to_list()) <= {"VER", "NOR"}


async def test_compare_with_explicit_lap_always_uses_free_tier_even_when_keyed(respx_mock, feed):
    _register_feed(respx_mock, feed)
    api = respx_mock.get(url__regex=r".*/api/v2/throttle-brake-comparison-data.*").mock(
        return_value=Response(200, json={})
    )
    async with AsyncClient(api_key="secret") as client:
        # lap1= explicit -> premium (which only supports "fastest lap") must be skipped.
        result = await client.session(YEAR, 2, "Q").compare("VER", "NOR", lap1=1, lap2=1)
    assert not api.called
    from t1f1.analysis import COMPARE_SCHEMA

    assert result.schema == COMPARE_SCHEMA


async def test_frame_cache_skips_refetching_telemetry_on_a_fresh_client(respx_mock, feed, tmp_path):
    routes = _register_feed(respx_mock, feed)
    car_data_route = routes[SESSION_URL + "CarData.z.jsonStream"]
    cache = DiskCache(tmp_path)

    async with AsyncClient(cache=cache) as client:
        first = await client.session(YEAR, 2, "Q").telemetry("VER")
    assert car_data_route.call_count == 1

    # A brand-new client (fresh in-memory RawF1Source) sharing the same disk cache
    # should serve the decoded frame straight off disk — no CarData re-fetch at all.
    async with AsyncClient(cache=cache) as client:
        second = await client.session(YEAR, 2, "Q").telemetry("VER")
    assert car_data_route.call_count == 1
    assert second.equals(first)


async def test_http_cache_skips_refetching_index_across_sessions(respx_mock, feed, tmp_path):
    routes = _register_feed(respx_mock, feed)
    index_route = routes[INDEX_URL]
    cache = DiskCache(tmp_path)

    async with AsyncClient(cache=cache) as client:
        await client.session(YEAR, 2, "Q").telemetry("VER")
        # A second, distinct session handle re-resolves Index.json from scratch, but
        # byte-level HTTP caching means it never actually hits the network for it.
        await client.session(YEAR, 2, "Q").weather()
    assert index_route.call_count == 1


async def test_driver_pace_falls_back_to_free_when_premium_upstream_fails(respx_mock, feed):
    _register_feed(respx_mock, feed)
    api = respx_mock.get(url__regex=r".*/api/v2/driver-pace-data.*").mock(
        return_value=Response(503, json={"error": "upstream_unavailable", "detail": "down"})
    )
    async with AsyncClient(api_key="secret") as client:
        session = client.session(YEAR, 2, "Q")
        result = await session.driver_pace()
    assert api.called
    assert session.last_source == "free"
    assert set(result["driver"].to_list()) <= {"VER", "NOR"}


async def test_driver_pace_reports_t1api_as_last_source_on_success(respx_mock, feed):
    _register_feed(respx_mock, feed)
    respx_mock.get(url__regex=r".*/api/v2/driver-pace-data.*").mock(
        return_value=Response(200, json={"drivers": []})
    )
    async with AsyncClient(api_key="secret") as client:
        session = client.session(YEAR, 2, "Q")
        await session.driver_pace()
    assert session.last_source == "t1api"


async def test_driver_standings_auth_error_propagates_instead_of_silently_falling_back(
    respx_mock,
):
    from t1f1.exceptions import AuthError

    t1api = respx_mock.get(url__regex=T1API_DRIVER_STANDINGS_ROUTE).mock(
        return_value=Response(403, json={"detail": "Invalid API key"})
    )
    ergast_route = respx_mock.get(ERGAST_DRIVER_STANDINGS_URL).mock(
        return_value=Response(200, json={})
    )
    async with AsyncClient(api_key="bad-key") as client:
        with pytest.raises(AuthError):
            await client.driver_standings(2024)
    assert t1api.called
    # A rejected key is a configuration mistake, not a "premium is briefly down"
    # situation — it must not be silently papered over by falling back to Ergast.
    assert not ergast_route.called


async def test_client_quota_reports_rate_limit_headers_from_t1api(respx_mock):
    respx_mock.get(url__regex=T1API_DRIVER_STANDINGS_ROUTE).mock(
        return_value=Response(
            200,
            json={"standings": []},
            headers={
                "X-RateLimit-Limit": "300",
                "X-RateLimit-Remaining": "299",
                "X-RateLimit-Reset": "1700000000",
            },
        )
    )
    async with AsyncClient(api_key="secret") as client:
        assert client.quota is None
        await client.driver_standings(2024)
        assert client.quota is not None
        assert client.quota.limit == 300
        assert client.quota.remaining == 299
        assert client.quota.reset == 1700000000


async def test_client_quota_is_none_without_a_key():
    async with AsyncClient() as client:
        assert client.quota is None
