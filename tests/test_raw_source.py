"""Free-tier RawF1Source end to end against the synthetic feed."""

from __future__ import annotations

import pytest
from httpx import Response

from t1f1 import AsyncClient
from t1f1.exceptions import SessionNotFoundError
from t1f1.schemas import TELEMETRY_SCHEMA

from .conftest import INDEX_URL, YEAR


def _register(respx_mock, feed):
    for url, content in feed.items():
        respx_mock.get(url).mock(return_value=Response(200, content=content))


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
