"""Season-index scraping + event/session fuzzy resolution."""

from __future__ import annotations

import pytest
from httpx import Response

from t1f1.config import ClientConfig
from t1f1.exceptions import SessionNotFoundError
from t1f1.ingestion.resolver import resolve_session
from t1f1.transport import AsyncTransport

from .conftest import INDEX_URL, SESSION_URL, YEAR


async def _resolve(gp, session):
    config = ClientConfig()
    async with AsyncTransport(source="livetiming", config=config) as transport:
        return await resolve_session(transport, config, YEAR, gp, session)


async def test_resolve_by_round_and_session_alias(respx_mock, index_json):
    respx_mock.get(INDEX_URL).mock(return_value=Response(200, json=index_json))
    ref = await _resolve(2, "q")  # round 2 = Italian GP; "q" -> Qualifying
    assert ref.base_url == SESSION_URL
    assert ref.event_name == "Italian Grand Prix"
    assert ref.session_name == "Qualifying"
    assert ref.round_number == 2


async def test_resolve_by_fuzzy_event_name(respx_mock, index_json):
    respx_mock.get(INDEX_URL).mock(return_value=Response(200, json=index_json))
    ref = await _resolve("monza", "qualifying")  # matches Location "Monza"
    assert ref.event_name == "Italian Grand Prix"


async def test_resolve_practice_alias(respx_mock, index_json):
    respx_mock.get(INDEX_URL).mock(return_value=Response(200, json=index_json))
    ref = await _resolve(2, "fp1")
    assert ref.session_name == "Practice 1"


async def test_round_out_of_range_raises(respx_mock, index_json):
    respx_mock.get(INDEX_URL).mock(return_value=Response(200, json=index_json))
    with pytest.raises(SessionNotFoundError) as exc:
        await _resolve(99, "q")
    assert exc.value.valid_rounds == [1, 2]


async def test_unknown_session_raises_with_suggestions(respx_mock, index_json):
    respx_mock.get(INDEX_URL).mock(return_value=Response(200, json=index_json))
    with pytest.raises(SessionNotFoundError) as exc:
        await _resolve(2, "sprint")
    assert "Qualifying" in exc.value.suggestions
