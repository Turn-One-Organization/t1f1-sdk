"""Free-tier data source: fetch & decode directly from the F1 live-timing feed.

Session-scoped. Resolves the session directory once, then lazily (and concurrently)
fetches the raw streams it needs, caching decoded records for the source's lifetime.
This is the client-side adaptation of the backend's ``F1StaticClient``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import polars as pl

from t1f1 import analysis
from t1f1.cache import CacheBackend
from t1f1.config import ClientConfig
from t1f1.exceptions import SessionNotFoundError, T1F1Error
from t1f1.frames.telemetry import add_distance, add_relative_distance, compute_driver_ahead
from t1f1.ingestion.decode import build_telemetry, decode_car_data, decode_position
from t1f1.ingestion.messages import (
    decode_race_control_messages,
    decode_session_status,
    decode_track_status,
    latest_total_laps,
)
from t1f1.ingestion.resolver import SessionRef, resolve_session
from t1f1.ingestion.results import build_results, segment_qualifying_laps
from t1f1.ingestion.session_clock import SessionClock, session_start_from_info
from t1f1.ingestion.stream import parse_compressed_stream, parse_jsonstream
from t1f1.ingestion.timing import attach_track_status, decode_laps
from t1f1.ingestion.weather import decode_weather
from t1f1.schemas import empty_telemetry
from t1f1.transport import AsyncTransport

#: Marker meaning "not yet computed" (distinct from a resolved value of ``None``).
_UNSET = object()

#: Substrings (lower-cased) of ``SessionRef.session_type`` that mean "has knockout
#: segments" — Q1/Q2/Q3 inference only applies to these.
_QUALIFYING_TYPE_HINTS = ("qualifying", "shootout")


class RawF1Source:
    """Serves telemetry, laps, results, and weather for one ``(year, gp, session)``
    from the official feed."""

    def __init__(
        self,
        transport: AsyncTransport,
        config: ClientConfig,
        year: int,
        gp: int | str,
        session: str,
        *,
        cache: CacheBackend | None = None,
    ) -> None:
        self._transport = transport
        self._config = config
        self._year = year
        self._gp = gp
        self._session = session
        self._cache = cache

        self._ref: SessionRef | None = None
        self._driver_info_cache: dict[str, dict[str, str]] | None = None
        self._drivers: dict[str, str] | None = None  # TLA (upper) -> racing number

        self._car_records: list[dict[str, Any]] | None = None
        self._pos_records: list[dict[str, Any]] | None = None
        self._telemetry_lock = asyncio.Lock()

        self._timing_records: list[dict[str, Any]] | None = None
        self._timing_app_records: list[dict[str, Any]] | None = None
        self._timing_lock = asyncio.Lock()

        self._weather_records: list[dict[str, Any]] | None = None
        self._weather_lock = asyncio.Lock()

        self._track_status_records: list[dict[str, Any]] | None = None
        self._session_status_records: list[dict[str, Any]] | None = None
        self._race_control_records: list[dict[str, Any]] | None = None
        self._lap_count_records: list[dict[str, Any]] | None = None
        self._messages_lock = asyncio.Lock()

        self._session_info: dict[str, Any] | None = None
        self._session_info_lock = asyncio.Lock()
        self._session_start: datetime | None | object = _UNSET
        self._session_start_lock = asyncio.Lock()

    async def _cached_frame(
        self, name: str, build: Callable[[], Awaitable[pl.DataFrame]]
    ) -> pl.DataFrame:
        """Decoded-frame cache around ``build()``, keyed by this session's resolved
        directory + ``name`` (e.g. ``"telemetry:44"``, ``"laps"``). A no-op passthrough
        when no cache was configured. Empty results are never cached — an empty frame
        usually means "not published yet", which we want re-checked on the next call
        rather than pinned as a false negative."""
        if self._cache is None:
            return await build()
        ref = await self.session_ref()
        key = f"{ref.base_url}#{name}"
        cached = await self._cache.get_frame(key)
        if cached is not None:
            return cached
        frame = await build()
        if not frame.is_empty():
            await self._cache.set_frame(key, frame)
        return frame

    # -- resolution & metadata ------------------------------------------------

    async def session_ref(self) -> SessionRef:
        if self._ref is None:
            self._ref = await resolve_session(
                self._transport, self._config, self._year, self._gp, self._session
            )
        return self._ref

    async def session_info(self) -> dict[str, Any]:
        """Fetch & cache ``SessionInfo.json``. Returns ``{}`` if unavailable rather
        than failing the whole session — it only feeds the clock-anchoring nicety."""
        if self._session_info is not None:
            return self._session_info
        async with self._session_info_lock:
            if self._session_info is not None:
                return self._session_info
            ref = await self.session_ref()
            try:
                info = await self._transport.get_json(ref.file_url("SessionInfo.json"))
            except T1F1Error:
                info = {}
            self._session_info = info if isinstance(info, dict) else {}
            return self._session_info

    async def _get_session_start(self) -> datetime | None:
        if self._session_start is _UNSET:
            async with self._session_start_lock:
                if self._session_start is _UNSET:
                    info = await self.session_info()
                    self._session_start = session_start_from_info(info) if info else None
        return self._session_start  # type: ignore[return-value]

    async def _driver_info(self) -> dict[str, dict[str, str]]:
        """Racing number -> ``{"tla": ..., "team": ...}``, from ``DriverList.json``."""
        if self._driver_info_cache is not None:
            return self._driver_info_cache
        ref = await self.session_ref()
        raw = await self._transport.get_json(ref.file_url("DriverList.json"))
        entries = raw.get("Drivers", raw) if isinstance(raw, dict) else {}
        info: dict[str, dict[str, str]] = {}
        for number, data in entries.items():
            if not isinstance(data, dict):
                continue
            tla = data.get("Tla") or data.get("RacingNumber") or number
            racing_number = str(data.get("RacingNumber", number))
            info[racing_number] = {"tla": str(tla).upper(), "team": data.get("TeamName")}
        self._driver_info_cache = info
        return info

    async def _driver_map(self) -> dict[str, str]:
        if self._drivers is not None:
            return self._drivers
        info = await self._driver_info()
        mapping = {data["tla"]: number for number, data in info.items()}
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
        async with self._telemetry_lock:
            if self._car_records is not None and self._pos_records is not None:
                return
            ref = await self.session_ref()
            car_text, pos_text = await asyncio.gather(
                self._transport.get_text(ref.file_url("CarData.z.jsonStream")),
                self._transport.get_text(ref.file_url("Position.z.jsonStream")),
            )
            self._car_records = parse_compressed_stream(car_text)
            self._pos_records = parse_compressed_stream(pos_text)

    async def _ensure_timing_streams(self) -> None:
        if self._timing_records is not None and self._timing_app_records is not None:
            return
        async with self._timing_lock:
            if self._timing_records is not None and self._timing_app_records is not None:
                return
            ref = await self.session_ref()
            timing_text, app_text = await asyncio.gather(
                self._transport.get_text(ref.file_url("TimingData.jsonStream")),
                self._transport.get_text(ref.file_url("TimingAppData.jsonStream")),
            )
            self._timing_records = parse_jsonstream(timing_text)
            self._timing_app_records = parse_jsonstream(app_text)

    async def _ensure_weather_stream(self) -> None:
        if self._weather_records is not None:
            return
        async with self._weather_lock:
            if self._weather_records is not None:
                return
            ref = await self.session_ref()
            text = await self._transport.get_text(ref.file_url("WeatherData.jsonStream"))
            self._weather_records = parse_jsonstream(text)

    async def _fetch_optional_stream(self, filename: str) -> list[dict[str, Any]]:
        """Fetch & parse a ``.jsonStream`` file that may not exist for this session
        type (e.g. ``LapCount.jsonStream`` is Race-only) — confirmed live: the CDN
        returns 403, not 404, for a missing object, so any feed error is treated as
        "no data" rather than failing the whole message-stream fetch."""
        ref = await self.session_ref()
        try:
            text = await self._transport.get_text(ref.file_url(filename))
        except T1F1Error:
            return []
        return parse_jsonstream(text)

    async def _ensure_messages_streams(self) -> None:
        if self._race_control_records is not None:
            return
        async with self._messages_lock:
            if self._race_control_records is not None:
                return
            (
                self._track_status_records,
                self._session_status_records,
                self._race_control_records,
                self._lap_count_records,
            ) = await asyncio.gather(
                self._fetch_optional_stream("TrackStatus.jsonStream"),
                self._fetch_optional_stream("SessionStatus.jsonStream"),
                self._fetch_optional_stream("RaceControlMessages.jsonStream"),
                self._fetch_optional_stream("LapCount.jsonStream"),
            )

    async def load(
        self,
        *,
        laps: bool = True,
        telemetry: bool = True,
        weather: bool = True,
        messages: bool = True,
    ) -> None:
        """Prefetch the requested stream groups concurrently.

        Every accessor below is self-sufficient (it fetches & caches on first use),
        so calling ``load()`` first is optional — it exists purely to gather several
        streams over the wire at once instead of on first access to each.
        """
        tasks = []
        if telemetry:
            tasks.append(self._ensure_telemetry_streams())
        if laps:
            tasks.append(self._ensure_timing_streams())
        if weather:
            tasks.append(self._ensure_weather_stream())
        if messages:
            tasks.append(self._ensure_messages_streams())
        if tasks:
            await asyncio.gather(*tasks)

    # -- DataSource interface: telemetry --------------------------------------

    async def telemetry(self, driver: str) -> pl.DataFrame:
        number = await self.resolve_driver_number(driver)

        async def _build() -> pl.DataFrame:
            await self._ensure_telemetry_streams()
            assert self._car_records is not None and self._pos_records is not None
            car_rows = decode_car_data(self._car_records, number)
            pos_rows = decode_position(self._pos_records, number)
            return build_telemetry(
                car_rows, pos_rows, driver=str(driver).upper(), driver_number=number
            )

        return await self._cached_frame(f"telemetry:{number}", _build)

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

    async def lap_telemetry(self, driver: str, lap_number: int) -> pl.DataFrame:
        """Telemetry for one specific lap, sliced by that lap's time window.

        ``distance``/``relative_distance`` are recomputed from scratch over the
        slice, so they're lap-relative (start at 0) rather than session-cumulative.
        Live-verified against a real race lap: distance integrates to ~5866 m for a
        lap at Monza (real length 5793 m).

        **Known limitation**, confirmed against live data: the window is
        ``[lap_start_time, next_lap_start_time)``, and ``lap_start_time`` is the
        timestamp of the record where the *previous* lap's ``LastLapTime`` fired.
        For laps immediately following a long gap (red flag, an extended pit-box
        stop reported as one multi-minute "lap") this can be measurably imprecise —
        the feed's broadcast catches up gradually rather than resuming exactly at
        that instant. Consecutive, gap-free laps (the common case) slice cleanly.
        """
        number = await self.resolve_driver_number(driver)
        laps = await self.laps()
        this_lap = laps.filter(
            (pl.col("driver_number") == number) & (pl.col("lap_number") == lap_number)
        )
        if this_lap.is_empty():
            return empty_telemetry()
        lap_start = this_lap.row(0, named=True)["lap_start_time"]

        tel = await self.telemetry(driver)
        if tel.is_empty() or lap_start is None:
            return empty_telemetry()

        next_lap = laps.filter(
            (pl.col("driver_number") == number) & (pl.col("lap_number") == lap_number + 1)
        )
        lap_end = next_lap.row(0, named=True)["lap_start_time"] if not next_lap.is_empty() else None

        sliced = tel.filter(pl.col("timestamp") >= lap_start)
        if lap_end is not None:
            sliced = sliced.filter(pl.col("timestamp") < lap_end)
        if sliced.is_empty():
            return sliced
        return add_relative_distance(add_distance(sliced))

    async def driver_ahead(self, driver: str) -> pl.DataFrame:
        """``driver``'s telemetry augmented with ``driver_ahead``/
        ``distance_to_driver_ahead`` computed against every other driver's session
        telemetry. Fetches all drivers, so it's noticeably more expensive than a
        plain :meth:`telemetry` call."""
        mapping = await self._driver_map()  # TLA -> racing number
        number = await self.resolve_driver_number(driver)
        target = await self.telemetry(driver)
        others: dict[str, pl.DataFrame] = {}
        for tla, racing_number in mapping.items():
            if racing_number == number:
                continue
            tel = await self.telemetry(tla)
            if not tel.is_empty():
                others[tla] = tel
        return compute_driver_ahead(target, others)

    # -- laps / results / weather / messages -----------------------------------

    async def laps(self) -> pl.DataFrame:
        async def _build() -> pl.DataFrame:
            await asyncio.gather(self._ensure_timing_streams(), self._ensure_messages_streams())
            assert self._timing_records is not None and self._timing_app_records is not None
            drivers = await self._driver_info()
            clock = SessionClock(await self._get_session_start())
            laps = decode_laps(
                self._timing_records, self._timing_app_records, drivers=drivers, clock=clock
            )
            track_status = decode_track_status(self._track_status_records or [], clock=clock)
            return attach_track_status(laps, track_status)

        return await self._cached_frame("laps", _build)

    async def results(self) -> pl.DataFrame:
        async def _build() -> pl.DataFrame:
            await asyncio.gather(self._ensure_timing_streams(), self._ensure_messages_streams())
            assert self._timing_records is not None and self._timing_app_records is not None
            drivers = await self._driver_info()
            ref = await self.session_ref()

            qualifying_segments = None
            if any(hint in ref.session_type.lower() for hint in _QUALIFYING_TYPE_HINTS):
                laps = await self.laps()
                clock = SessionClock(await self._get_session_start())
                session_status = decode_session_status(
                    self._session_status_records or [], clock=clock
                )
                qualifying_segments = segment_qualifying_laps(laps, session_status)

            return build_results(
                self._timing_records,
                self._timing_app_records,
                drivers=drivers,
                qualifying_segments=qualifying_segments,
            )

        return await self._cached_frame("results", _build)

    async def weather(self) -> pl.DataFrame:
        async def _build() -> pl.DataFrame:
            await self._ensure_weather_stream()
            clock = SessionClock(await self._get_session_start())
            return decode_weather(self._weather_records or [], clock=clock)

        return await self._cached_frame("weather", _build)

    async def race_control_messages(self) -> pl.DataFrame:
        await self._ensure_messages_streams()
        clock = SessionClock(await self._get_session_start())
        return decode_race_control_messages(self._race_control_records or [], clock=clock)

    async def track_status(self) -> pl.DataFrame:
        await self._ensure_messages_streams()
        clock = SessionClock(await self._get_session_start())
        return decode_track_status(self._track_status_records or [], clock=clock)

    async def session_status(self) -> pl.DataFrame:
        await self._ensure_messages_streams()
        clock = SessionClock(await self._get_session_start())
        return decode_session_status(self._session_status_records or [], clock=clock)

    async def total_laps(self) -> int | None:
        await self._ensure_messages_streams()
        total = latest_total_laps(self._lap_count_records or [])
        if total is not None:
            return total
        laps = await self.laps()
        if laps.is_empty():
            return None
        return int(laps["lap_number"].max())

    # -- analysis suite: computed locally from laps()/telemetry() --------------

    async def _fastest_lap_number(self, driver: str) -> int | None:
        number = await self.resolve_driver_number(driver)
        laps = await self.laps()
        driver_laps = laps.filter(
            (pl.col("driver_number") == number) & pl.col("lap_time").is_not_null()
        )
        if driver_laps.is_empty():
            return None
        return driver_laps.sort("lap_time").row(0, named=True)["lap_number"]

    async def speed_trap_top_speeds(self) -> pl.DataFrame:
        return analysis.speed_trap_top_speeds(await self.laps())

    async def driver_pace(self, *, threshold: float = 1.07) -> pl.DataFrame:
        return analysis.driver_pace(await self.laps(), threshold=threshold)

    async def teams_pace(self, *, threshold: float = 1.07) -> pl.DataFrame:
        return analysis.teams_pace(await self.laps(), threshold=threshold)

    async def tyre_stints(self) -> pl.DataFrame:
        return analysis.tyre_stints(await self.laps())

    async def qualifying_results(self) -> pl.DataFrame:
        return analysis.qualifying_results(await self.results())

    async def speed_distribution(
        self, driver: str | None = None, *, bins: int = 20
    ) -> pl.DataFrame:
        if driver is not None:
            telemetry = await self.telemetry(driver)
        else:
            mapping = await self._driver_map()
            frames: list[pl.DataFrame] = []
            for tla in mapping:
                tel = await self.telemetry(tla)
                if not tel.is_empty():
                    frames.append(tel)
            telemetry = pl.concat(frames, how="vertical") if frames else empty_telemetry()
        return analysis.speed_distribution(telemetry, bins=bins)

    async def _fastest_lap_telemetry_pair(
        self, driver1: str, driver2: str, lap1: int | None, lap2: int | None
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        lap1 = lap1 if lap1 is not None else await self._fastest_lap_number(driver1)
        lap2 = lap2 if lap2 is not None else await self._fastest_lap_number(driver2)
        if lap1 is None or lap2 is None:
            return empty_telemetry(), empty_telemetry()
        return await self.lap_telemetry(driver1, lap1), await self.lap_telemetry(driver2, lap2)

    async def compare(
        self, driver1: str, driver2: str, *, lap1: int | None = None, lap2: int | None = None
    ) -> pl.DataFrame:
        """Distance-aligned speed/throttle/brake + time-delta comparison of two
        drivers' laps (their fastest lap each, by default).

        Confirmed live: correct and well-aligned (305 matched samples, sensible
        delta trend) when both laps fall inside the available CarData/Position
        window. Returns an **empty** frame — not an error — for a lap outside that
        window; this method (and :meth:`track_dominance`/:meth:`throttle_comparison`/
        :meth:`lap_time_analysis`, which share the same lap-telemetry lookup) inherit
        :meth:`lap_telemetry`'s documented CarData-coverage-gap limitation, and
        "fastest lap" auto-selection has no way to know in advance whether that
        particular lap happens to fall outside it.
        """
        tel1, tel2 = await self._fastest_lap_telemetry_pair(driver1, driver2, lap1, lap2)
        return analysis.compare(tel1, tel2)

    async def track_dominance(
        self,
        driver1: str,
        driver2: str,
        *,
        lap1: int | None = None,
        lap2: int | None = None,
        n_minisectors: int = 25,
    ) -> pl.DataFrame:
        tel1, tel2 = await self._fastest_lap_telemetry_pair(driver1, driver2, lap1, lap2)
        return analysis.track_dominance(
            tel1,
            tel2,
            driver1=str(driver1).upper(),
            driver2=str(driver2).upper(),
            n_minisectors=n_minisectors,
        )

    async def throttle_comparison(
        self, driver1: str, driver2: str, *, lap1: int | None = None, lap2: int | None = None
    ) -> pl.DataFrame:
        full = await self.compare(driver1, driver2, lap1=lap1, lap2=lap2)
        return full.select(["distance", "delta_seconds", "driver1_throttle", "driver2_throttle"])

    async def lap_time_analysis(
        self, driver1: str, driver2: str, *, lap1: int | None = None, lap2: int | None = None
    ) -> pl.DataFrame:
        full = await self.compare(driver1, driver2, lap1=lap1, lap2=lap2)
        return full.select(["distance", "delta_seconds", "driver1_speed_kmh", "driver2_speed_kmh"])
