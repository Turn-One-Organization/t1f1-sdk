"""circuit.py: T1API-only circuit reference data."""

from __future__ import annotations

from httpx import Response

from t1f1.circuit import get_circuit_info, list_circuits
from t1f1.config import ClientConfig
from t1f1.schemas import CIRCUIT_CORNER_SCHEMA
from t1f1.transport import AsyncTransport

CONFIG = ClientConfig()


async def test_get_circuit_info_parses_corners(respx_mock):
    payload = {
        "data": {
            "corners": [
                {
                    "number": 1,
                    "letter": "",
                    "x": 100.0,
                    "y": 200.0,
                    "angle": 90.0,
                    "distance": 350.0,
                },
                {
                    "number": 2,
                    "letter": "a",
                    "x": 150.0,
                    "y": 250.0,
                    "angle": -45.0,
                    "distance": 700.0,
                },
            ],
            "rotation": 45.0,
        }
    }
    respx_mock.get(CONFIG.t1api_url("/api/static/circuits/1/data")).mock(
        return_value=Response(200, json=payload)
    )
    transport = AsyncTransport(source="t1api", config=CONFIG, base_headers={"X-API-Key": "k"})
    info = await get_circuit_info(transport, CONFIG, 1)
    await transport.aclose()

    assert info.corners.schema == CIRCUIT_CORNER_SCHEMA
    assert info.corners.height == 2
    assert info.corners["number"].to_list() == [1, 2]
    assert info.rotation == 45.0


async def test_get_circuit_info_missing_fields_returns_empty_corners(respx_mock):
    respx_mock.get(CONFIG.t1api_url("/api/static/circuits/1/data")).mock(
        return_value=Response(200, json={"data": {}})
    )
    transport = AsyncTransport(source="t1api", config=CONFIG, base_headers={"X-API-Key": "k"})
    info = await get_circuit_info(transport, CONFIG, 1)
    await transport.aclose()
    assert info.corners.is_empty()
    assert info.corners.schema == CIRCUIT_CORNER_SCHEMA


async def test_list_circuits(respx_mock):
    respx_mock.get(CONFIG.t1api_url("/api/static/circuits?year=2026")).mock(
        return_value=Response(200, json={"circuits": [{"id": 1, "name": "Monza"}]})
    )
    transport = AsyncTransport(source="t1api", config=CONFIG, base_headers={"X-API-Key": "k"})
    circuits = await list_circuits(transport, CONFIG, 2026)
    await transport.aclose()
    assert circuits == [{"id": 1, "name": "Monza"}]
