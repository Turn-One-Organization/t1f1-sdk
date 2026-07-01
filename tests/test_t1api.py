"""Premium T1APISource: analysis via the API, telemetry delegated to raw."""

from __future__ import annotations

import pytest
from httpx import Response

from t1f1 import AsyncClient
from t1f1.exceptions import AuthError

from .conftest import YEAR

TOP_SPEED_ROUTE = r".*/api/v2/top-speed-telemetry-data.*"


def _register_feed(respx_mock, feed):
    for url, content in feed.items():
        respx_mock.get(url).mock(return_value=Response(200, content=content))


async def test_top_speeds_hits_api_and_sends_key(respx_mock, top_speed_payload):
    route = respx_mock.get(url__regex=TOP_SPEED_ROUTE).mock(
        return_value=Response(200, json=top_speed_payload)
    )
    async with AsyncClient(api_key="secret-key") as client:
        result = await client.session(YEAR, 2, "Q").top_speeds()

    assert route.called
    assert route.calls[0].request.headers["X-API-Key"] == "secret-key"
    assert result["driver"].to_list() == ["VER", "NOR"]
    assert result["top_speed_kmh"].to_list() == pytest.approx([355.0, 340.0])


async def test_telemetry_still_uses_raw_feed_when_keyed(respx_mock, feed):
    _register_feed(respx_mock, feed)
    api = respx_mock.get(url__regex=TOP_SPEED_ROUTE).mock(return_value=Response(200, json={}))
    async with AsyncClient(api_key="secret-key") as client:
        tel = await client.session(YEAR, 2, "Q").telemetry("VER")

    assert tel.height == 3  # served by the raw feed
    assert not api.called  # telemetry never touches the API


async def test_auth_error_surfaces(respx_mock):
    respx_mock.get(url__regex=TOP_SPEED_ROUTE).mock(
        return_value=Response(403, json={"detail": "Invalid API key"})
    )
    async with AsyncClient(api_key="bad") as client:
        with pytest.raises(AuthError):
            await client.session(YEAR, 2, "Q").top_speeds()
