"""Circuit reference data (corners, marshal lights/sectors, rotation) — T1API only.

The free F1 live-timing feed carries no static circuit geometry, so unlike Modules
1-3's raw-feed-first design, this module has **no free-tier fallback** — it's served
exclusively by T1API's ``/api/static/circuits/*`` endpoints.

**Not live-verified.** T1API's own docs describe ``/circuits/{id}/data`` only as
"Full circuit data incl. layout files -> {"data": ...}" with no field-level shape,
and this project has no T1API credentials to test against the real service. Parsing
below targets fastf1's well-known ``CircuitInfo`` shape (corners / marshal_lights /
marshal_sectors / rotation) defensively (tries a few plausible key-name casings), but
should be treated as unverified until checked against a real response.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from t1f1.config import ClientConfig
from t1f1.schemas import CIRCUIT_CORNER_SCHEMA, empty_circuit_corners
from t1f1.transport import AsyncTransport


def _pick(d: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in d:
            return d[key]
    return None


def _decode_points(entries: list[Any]) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rows.append(
            {
                "number": _pick(entry, "number", "Number"),
                "letter": _pick(entry, "letter", "Letter") or "",
                "x": _pick(entry, "x", "X"),
                "y": _pick(entry, "y", "Y"),
                "angle": _pick(entry, "angle", "Angle"),
                "distance": _pick(entry, "distance", "Distance"),
            }
        )
    if not rows:
        return empty_circuit_corners()
    return pl.DataFrame(rows, schema=CIRCUIT_CORNER_SCHEMA)


class CircuitInfo:
    """Corners / marshal lights / marshal sectors / rotation for one circuit.

    ``marshal_lights``/``marshal_sectors`` are kept as plain, loosely-typed
    ``pl.DataFrame``s (whatever columns the payload actually had) rather than a
    rigid schema — see the module docstring's live-verification caveat.
    """

    def __init__(
        self,
        corners: pl.DataFrame,
        marshal_lights: pl.DataFrame,
        marshal_sectors: pl.DataFrame,
        rotation: float | None,
    ) -> None:
        self.corners = corners
        self.marshal_lights = marshal_lights
        self.marshal_sectors = marshal_sectors
        self.rotation = rotation


async def get_circuit_info(
    transport: AsyncTransport,
    config: ClientConfig,
    circuit_id: int | str,
    *,
    year: int | None = None,
) -> CircuitInfo:
    """Fetch corner/marshal-point geometry for one circuit (T1API only)."""
    params = f"?year={year}" if year is not None else ""
    payload = await transport.get_json(
        config.t1api_url(f"/api/static/circuits/{circuit_id}/data{params}")
    )
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    corners = _decode_points(_pick(data, "corners", "Corners") or [])
    marshal_lights = pl.DataFrame(_pick(data, "marshal_lights", "MarshalLights") or [])
    marshal_sectors = pl.DataFrame(_pick(data, "marshal_sectors", "MarshalSectors") or [])
    rotation = _pick(data, "rotation", "Rotation")
    return CircuitInfo(corners, marshal_lights, marshal_sectors, rotation)


async def list_circuits(
    transport: AsyncTransport, config: ClientConfig, year: int
) -> list[dict[str, Any]]:
    """All circuits for ``year`` (T1API only). Raw entries — see module caveat."""
    payload = await transport.get_json(config.t1api_url(f"/api/static/circuits?year={year}"))
    return payload.get("circuits", []) if isinstance(payload, dict) else []
