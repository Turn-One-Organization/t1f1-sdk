"""Client wiring: dual-tier routing and sync/async parity."""

from __future__ import annotations

import pytest
from httpx import Response

from t1f1 import AsyncClient, Client

from .conftest import YEAR

TOP_SPEED_ROUTE = r".*/api/v2/top-speed-telemetry-data.*"


def _register_feed(respx_mock, feed):
    for url, content in feed.items():
        respx_mock.get(url).mock(return_value=Response(200, content=content))


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
