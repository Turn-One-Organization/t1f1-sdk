"""Premium data source: verified/enriched analysis products from api.t1f1.com.

Only the *analysis* methods hit the API — the T1API has no raw per-sample telemetry
endpoint, so ``telemetry`` delegates to the injected :class:`RawF1Source`. This is the
"hybrid at the analysis level" design decision.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from t1f1.config import ClientConfig
from t1f1.sources.raw_f1 import RawF1Source
from t1f1.transport import AsyncTransport

#: Header name the T1API expects for authentication.
API_KEY_HEADER = "X-API-Key"


class T1APISource:
    """Routes analysis products to ``/api/v2/*-data``; telemetry falls back to raw."""

    def __init__(
        self,
        transport: AsyncTransport,
        config: ClientConfig,
        year: int,
        gp: int | str,
        session: str,
        *,
        raw: RawF1Source,
    ) -> None:
        self._transport = transport
        self._config = config
        self._year = year
        self._gp = gp
        self._session = session
        self._raw = raw

    def _url(self, endpoint: str) -> str:
        params = f"year={self._year}&gp={self._gp}&session={self._session}"
        return self._config.t1api_url(f"/api/v2/{endpoint}?{params}")

    # -- raw telemetry: no API endpoint, delegate to the free engine ----------

    async def telemetry(self, driver: str) -> pl.DataFrame:
        return await self._raw.telemetry(driver)

    # -- analysis products: served by the API ---------------------------------

    async def top_speeds(self) -> pl.DataFrame:
        payload: dict[str, Any] = await self._transport.get_json(
            self._url("top-speed-telemetry-data")
        )
        drivers = payload.get("drivers", []) if isinstance(payload, dict) else []
        if not drivers:
            return pl.DataFrame(schema={"driver": pl.Utf8, "top_speed_kmh": pl.Float32})
        return (
            pl.DataFrame(drivers)
            .select(
                pl.col("driver").cast(pl.Utf8),
                pl.col("top_speed_kmh").cast(pl.Float32),
                *([pl.col("lap").cast(pl.Int32)] if "lap" in drivers[0] else []),
            )
            .sort("top_speed_kmh", descending=True)
        )
