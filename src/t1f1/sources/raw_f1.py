"""Free-tier data source: fetch & decode directly from the F1 live-timing feed.

Session-scoped. Resolves the session directory once, then lazily (and concurrently)
fetches the raw streams it needs, caching decoded records for the source's lifetime.
This is the client-side adaptation of the backend's ``F1StaticClient``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import polars as pl

from t1f1.config import ClientConfig
from t1f1.exceptions import SessionNotFoundError
from t1f1.ingestion.decode import build_telemetry, decode_car_data, decode_position
from t1f1.ingestion.resolver import SessionRef, resolve_session
from t1f1.ingestion.stream import parse_compressed_stream
from t1f1.schemas import empty_telemetry
from t1f1.transport import AsyncTransport


class RawF1Source:
    """Serves telemetry for one ``(year, gp, session)`` from the official feed."""

    def __init__(
        self,
        transport: AsyncTransport,
        config: ClientConfig,
        year: int,
        gp: int | str,
        session: str,
    ) -> None:
        self._transport = transport
        self._config = config
        self._year = year
        self._gp = gp
        self._session = session

        self._ref: SessionRef | None = None
        self._drivers: dict[str, str] | None = None  # TLA (upper) -> racing number
        self._car_records: list[dict[str, Any]] | None = None
        self._pos_records: list[dict[str, Any]] | None = None
        self._lock = asyncio.Lock()

    # -- resolution & metadata ------------------------------------------------

    async def session_ref(self) -> SessionRef:
        if self._ref is None:
            self._ref = await resolve_session(
                self._transport, self._config, self._year, self._gp, self._session
            )
        return self._ref

    async def _driver_map(self) -> dict[str, str]:
        if self._drivers is not None:
            return self._drivers
        ref = await self.session_ref()
        raw = await self._transport.get_json(ref.file_url("DriverList.json"))
        entries = raw.get("Drivers", raw) if isinstance(raw, dict) else {}
        mapping: dict[str, str] = {}
        for number, info in entries.items():
            if not isinstance(info, dict):
                continue
            tla = info.get("Tla") or info.get("RacingNumber") or number
            racing_number = str(info.get("RacingNumber", number))
            mapping[str(tla).upper()] = racing_number
        self._drivers = mapping
        return mapping

    async def resolve_driver_number(self, driver: str) -> str:
        """Map a driver identifier (TLA or number) to a racing number."""
        driver = str(driver).strip()
        mapping = await self._driver_map()
        if driver.upper() in mapping:
            return mapping[driver.upper()]
        if driver in mapping.values():
            return driver
        raise SessionNotFoundError(
            year=self._year,
            gp=self._gp,
            session=self._session,
            reason=f"Unknown driver {driver!r}",
            suggestions=sorted(mapping),
        )

    # -- raw stream loading ---------------------------------------------------

    async def _ensure_telemetry_streams(self) -> None:
        if self._car_records is not None and self._pos_records is not None:
            return
        async with self._lock:
            if self._car_records is not None and self._pos_records is not None:
                return
            ref = await self.session_ref()
            car_text, pos_text = await asyncio.gather(
                self._transport.get_text(ref.file_url("CarData.z.jsonStream")),
                self._transport.get_text(ref.file_url("Position.z.jsonStream")),
            )
            self._car_records = parse_compressed_stream(car_text)
            self._pos_records = parse_compressed_stream(pos_text)

    # -- DataSource interface -------------------------------------------------

    async def telemetry(self, driver: str) -> pl.DataFrame:
        number = await self.resolve_driver_number(driver)
        await self._ensure_telemetry_streams()
        assert self._car_records is not None and self._pos_records is not None
        car_rows = decode_car_data(self._car_records, number)
        pos_rows = decode_position(self._pos_records, number)
        return build_telemetry(car_rows, pos_rows, driver=str(driver).upper(), driver_number=number)

    async def top_speeds(self) -> pl.DataFrame:
        """Compute peak speed per driver locally from telemetry."""
        mapping = await self._driver_map()
        await self._ensure_telemetry_streams()
        rows: list[dict[str, Any]] = []
        for tla in mapping:
            tel = await self.telemetry(tla)
            if tel.is_empty():
                continue
            rows.append({"driver": tla, "top_speed_kmh": tel["speed_kmh"].max()})
        if not rows:
            return pl.DataFrame(schema={"driver": pl.Utf8, "top_speed_kmh": pl.Float32})
        return (
            pl.DataFrame(rows)
            .with_columns(pl.col("top_speed_kmh").cast(pl.Float32))
            .sort("top_speed_kmh", descending=True)
        )

    async def empty(self) -> pl.DataFrame:
        return empty_telemetry()
