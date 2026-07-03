"""Premium data source: verified/enriched analysis products from api.t1f1.com.

Only the *analysis* methods hit the API — the T1API has no raw per-sample telemetry
endpoint, so ``telemetry`` delegates to the injected :class:`RawF1Source`. This is the
"hybrid at the analysis level" design decision.

**Analysis methods below are not live-verified.** ``api-docs/`` documents each
endpoint's method/path/params but not its response *field names* (beyond
``top-speed-telemetry-data``, ported from Module 1's live-tested payload), and this
project has no T1API credentials to check a real response against. Where the target
shape is a reasonable guess (pace/stint/results tables), we cast into the same
schema the free-tier equivalent uses; where it isn't (comparison/distribution
payloads), we return whatever records the response actually contains rather than
force a possibly-wrong cast. Treat all of it as needing a pass once a key is
available — see [[live-validation-catches-feed-quirks]] for why that matters.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from t1f1.analysis import PACE_SCHEMA, SPEED_TRAP_SCHEMA, STINT_SCHEMA, TEAM_PACE_SCHEMA
from t1f1.config import ClientConfig
from t1f1.schemas import RESULTS_SCHEMA
from t1f1.sources.raw_f1 import RawF1Source
from t1f1.transport import AsyncTransport

#: Header name the T1API expects for authentication.
API_KEY_HEADER = "X-API-Key"


def _records(payload: Any, *keys: str) -> list[dict[str, Any]]:
    """Pull a list of records out of a T1API payload, trying a few plausible
    top-level wrapper keys (docs don't specify one consistently)."""
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _cast_or_passthrough(
    rows: list[dict[str, Any]], schema: dict[str, pl.DataType]
) -> pl.DataFrame:
    """Cast into ``schema`` if the records look compatible; otherwise return them
    as a loosely-typed frame rather than raise on an unexpected T1API shape."""
    if not rows:
        return pl.DataFrame(schema=schema)
    frame = pl.DataFrame(rows)
    try:
        return frame.select(list(schema)).cast(schema)
    except pl.exceptions.PolarsError:
        return frame


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

    def _url(self, endpoint: str, **extra: str) -> str:
        params = f"year={self._year}&gp={self._gp}&session={self._session}"
        for key, value in extra.items():
            params += f"&{key}={value}"
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

    async def speed_trap_top_speeds(self) -> pl.DataFrame:
        payload = await self._transport.get_json(self._url("top-speed-st-data"))
        return _cast_or_passthrough(_records(payload, "drivers", "data"), SPEED_TRAP_SCHEMA)

    async def driver_pace(self) -> pl.DataFrame:
        payload = await self._transport.get_json(self._url("driver-pace-data"))
        return _cast_or_passthrough(_records(payload, "drivers", "data"), PACE_SCHEMA)

    async def teams_pace(self) -> pl.DataFrame:
        payload = await self._transport.get_json(self._url("teams-pace-data"))
        return _cast_or_passthrough(_records(payload, "teams", "data"), TEAM_PACE_SCHEMA)

    async def tyre_stints(self) -> pl.DataFrame:
        payload = await self._transport.get_json(self._url("tyre-stint-usage-data"))
        return _cast_or_passthrough(_records(payload, "drivers", "stints", "data"), STINT_SCHEMA)

    async def qualifying_results(self) -> pl.DataFrame:
        payload = await self._transport.get_json(self._url("qualifying-results-data"))
        return _cast_or_passthrough(_records(payload, "results", "drivers", "data"), RESULTS_SCHEMA)

    async def speed_distribution(self, driver: str | None = None) -> pl.DataFrame:
        extra = {"driver": driver} if driver else {}
        payload = await self._transport.get_json(self._url("speed-distribution-data", **extra))
        rows = _records(payload, "bins", "data")
        return pl.DataFrame(rows) if rows else pl.DataFrame()

    async def compare(self, driver1: str, driver2: str) -> pl.DataFrame:
        # Closest documented match for a general two-driver comparison.
        return await self.throttle_comparison(driver1, driver2)

    async def throttle_comparison(self, driver1: str, driver2: str) -> pl.DataFrame:
        payload = await self._transport.get_json(
            self._url("throttle-brake-comparison-data", d1=driver1, d2=driver2)
        )
        rows = _records(payload, "samples", "data")
        return pl.DataFrame(rows) if rows else pl.DataFrame()

    async def lap_time_analysis(self, driver1: str, driver2: str) -> pl.DataFrame:
        payload = await self._transport.get_json(
            self._url("lap-time-analysis-data", d1=driver1, d2=driver2)
        )
        rows = _records(payload, "samples", "data")
        return pl.DataFrame(rows) if rows else pl.DataFrame()

    async def track_dominance(self, driver1: str, driver2: str) -> pl.DataFrame:
        payload = await self._transport.get_json(
            self._url("track-comparison-data", d1=driver1, d2=driver2)
        )
        rows = _records(payload, "minisectors", "data")
        return pl.DataFrame(rows) if rows else pl.DataFrame()
