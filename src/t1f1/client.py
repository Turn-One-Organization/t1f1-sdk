"""Client objects: the entry point that wires transports and sources together.

``AsyncClient`` is the async core; ``Client`` is a blocking facade. Passing an
``api_key`` enables the premium tier (analysis products served by ``api.t1f1.com``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import polars as pl

from t1f1 import ergast
from t1f1._sync import LoopThread
from t1f1.cache import CacheBackend
from t1f1.circuit import CircuitInfo
from t1f1.circuit import get_circuit_info as _fetch_circuit_info
from t1f1.circuit import list_circuits as _fetch_circuits
from t1f1.config import ClientConfig
from t1f1.events import get_event as _fetch_event
from t1f1.events import get_event_schedule as _fetch_event_schedule
from t1f1.events import get_event_sessions as _fetch_event_sessions
from t1f1.events import get_events_remaining as _fetch_events_remaining
from t1f1.exceptions import PREMIUM_FALLBACK_ERRORS, AuthError
from t1f1.schemas import (
    CONSTRUCTOR_STANDINGS_SCHEMA,
    DRIVER_STANDINGS_SCHEMA,
    empty_constructor_standings,
    empty_driver_standings,
)
from t1f1.session import AsyncSession, Session
from t1f1.sources.raw_f1 import RawF1Source
from t1f1.sources.t1api import API_KEY_HEADER, T1APISource
from t1f1.transport import AsyncTransport, QuotaInfo


def _parse_t1api_driver_standings(payload: Any) -> pl.DataFrame:
    entries = payload.get("standings", []) if isinstance(payload, dict) else []
    rows = [
        {
            "position": e.get("position"),
            "driver": e.get("driver_code"),
            "driver_id": None,
            "full_name": e.get("driver_name"),
            "team": e.get("team"),
            "nationality": e.get("nationality"),
            "points": e.get("points"),
            "wins": e.get("wins"),
        }
        for e in entries
    ]
    if not rows:
        return empty_driver_standings()
    return pl.DataFrame(rows, schema=DRIVER_STANDINGS_SCHEMA)


def _parse_t1api_constructor_standings(payload: Any) -> pl.DataFrame:
    entries = payload.get("standings", []) if isinstance(payload, dict) else []
    rows = [
        {
            "position": e.get("position"),
            "team": e.get("team"),
            "team_id": None,
            "nationality": e.get("nationality"),
            "points": e.get("points"),
            "wins": e.get("wins"),
        }
        for e in entries
    ]
    if not rows:
        return empty_constructor_standings()
    return pl.DataFrame(rows, schema=CONSTRUCTOR_STANDINGS_SCHEMA)


class AsyncClient:
    """Async F1 telemetry client.

    Parameters
    ----------
    api_key:
        When provided, analysis methods are served by ``api.t1f1.com``.
    config:
        Base URLs, timeouts, and retry policy.
    cache:
        Optional :class:`~t1f1.cache.CacheBackend` (see :func:`t1f1.cache.enable_cache`).
        When set, every transport (F1 feed, T1API, Ergast) gets byte-level HTTP
        caching, and each session's ``telemetry``/``laps``/``results``/``weather``
        additionally caches its fully-decoded frame — a warm reload skips the network
        and re-decoding entirely.
    f1_client / t1api_client / ergast_client:
        Optionally inject ``httpx.AsyncClient`` instances (used by tests with
        ``httpx.MockTransport``). When injected, the caller owns their lifecycle.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        config: ClientConfig | None = None,
        cache: CacheBackend | None = None,
        f1_client: httpx.AsyncClient | None = None,
        t1api_client: httpx.AsyncClient | None = None,
        ergast_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config or ClientConfig()
        self._api_key = api_key
        self._cache = cache
        #: Which tier served the most recently completed dual-tier season-level call
        #: (``driver_standings``/``constructor_standings``): ``"t1api"`` or
        #: ``"ergast"``. ``None`` before any such call. Not meaningful under
        #: concurrent overlapping calls — it's a simple last-write, not per-call state.
        self.last_source: str | None = None

        self._f1_transport = AsyncTransport(
            source="livetiming",
            config=self._config,
            base_headers=self._config.f1_headers,
            client=f1_client,
            cache=cache,
        )
        #: jolpica-f1/Ergast: free, public, no key needed — always available.
        self._ergast_transport = AsyncTransport(
            source="ergast",
            config=self._config,
            client=ergast_client,
            cache=cache,
        )
        self._t1api_transport: AsyncTransport | None = None
        if api_key:
            self._t1api_transport = AsyncTransport(
                source="t1api",
                config=self._config,
                base_headers={API_KEY_HEADER: api_key},
                client=t1api_client,
                cache=cache,
            )

    @property
    def is_premium(self) -> bool:
        return self._t1api_transport is not None

    @property
    def quota(self) -> QuotaInfo | None:
        """Rate-limit usage T1API reported on its most recent response, or ``None``
        without a key / before any premium request has actually hit the network."""
        if self._t1api_transport is None:
            return None
        return self._t1api_transport.last_quota

    def session(self, year: int, gp: int | str, session: str) -> AsyncSession:
        """Build a session handle. Resolution/fetching happens lazily on first use."""
        raw = RawF1Source(self._f1_transport, self._config, year, gp, session, cache=self._cache)
        premium: T1APISource | None = None
        if self._t1api_transport is not None:
            premium = T1APISource(self._t1api_transport, self._config, year, gp, session, raw=raw)
        return AsyncSession(year, gp, session, raw=raw, premium=premium)

    async def aclose(self) -> None:
        await self._f1_transport.aclose()
        await self._ergast_transport.aclose()
        if self._t1api_transport is not None:
            await self._t1api_transport.aclose()
        if self._cache is not None:
            await self._cache.aclose()

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # -- events: season schedule (free tier only — see events.py docstring) ---

    async def event_schedule(self, year: int) -> pl.DataFrame:
        return await _fetch_event_schedule(self._f1_transport, self._config, year)

    async def event(self, year: int, gp: int | str) -> dict[str, Any]:
        return await _fetch_event(self._f1_transport, self._config, year, gp)

    async def event_sessions(self, year: int, gp: int | str) -> pl.DataFrame:
        return await _fetch_event_sessions(self._f1_transport, self._config, year, gp)

    async def events_remaining(self, year: int, *, after: datetime | None = None) -> pl.DataFrame:
        return await _fetch_events_remaining(self._f1_transport, self._config, year, after=after)

    # -- standings/results: T1API preferred if keyed, else jolpica-f1/Ergast --

    async def driver_standings(
        self, year: int, round: int | None = None
    ) -> pl.DataFrame:  # noqa: A002
        if self._t1api_transport is not None:
            try:
                url = self._t1api_standings_url("drivers", year, round)
                result = _parse_t1api_driver_standings(await self._t1api_transport.get_json(url))
                self.last_source = "t1api"
                return result
            except PREMIUM_FALLBACK_ERRORS:
                pass  # premium had a bad moment — fall back to the free path below
        result = await ergast.driver_standings(self._ergast_transport, self._config, year, round)
        self.last_source = "ergast"
        return result

    async def constructor_standings(
        self, year: int, round: int | None = None
    ) -> pl.DataFrame:  # noqa: A002
        if self._t1api_transport is not None:
            try:
                url = self._t1api_standings_url("constructors", year, round)
                result = _parse_t1api_constructor_standings(
                    await self._t1api_transport.get_json(url)
                )
                self.last_source = "t1api"
                return result
            except PREMIUM_FALLBACK_ERRORS:
                pass
        result = await ergast.constructor_standings(
            self._ergast_transport, self._config, year, round
        )
        self.last_source = "ergast"
        return result

    async def race_results(self, year: int, round: int) -> pl.DataFrame:  # noqa: A002
        # No T1API endpoint for raw classified race results — always Ergast.
        return await ergast.race_results(self._ergast_transport, self._config, year, round)

    def _t1api_standings_url(self, kind: str, year: int, round: int | None) -> str:  # noqa: A002
        if round is None:
            return self._config.t1api_url(f"/api/v2/seasons/{year}/{kind}-standings")
        return self._config.t1api_url(f"/api/v2/seasons/{year}/round/{round}/{kind}-standings")

    # -- circuit info: T1API only (no free-tier circuit geometry source) ------

    async def circuit_info(self, circuit_id: int | str, *, year: int | None = None) -> CircuitInfo:
        if self._t1api_transport is None:
            raise AuthError(
                "circuit_info() requires a T1API key (no free-tier circuit geometry source)"
            )
        return await _fetch_circuit_info(self._t1api_transport, self._config, circuit_id, year=year)

    async def circuits(self, year: int) -> list[dict[str, Any]]:
        if self._t1api_transport is None:
            raise AuthError(
                "circuits() requires a T1API key (no free-tier circuit geometry source)"
            )
        return await _fetch_circuits(self._t1api_transport, self._config, year)


class Client:
    """Blocking facade over :class:`AsyncClient`."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        config: ClientConfig | None = None,
        cache: CacheBackend | None = None,
    ) -> None:
        self._loop = LoopThread()
        self._inner = self._loop.run(_make_async_client(api_key, config, cache))

    @property
    def is_premium(self) -> bool:
        return self._inner.is_premium

    @property
    def quota(self) -> QuotaInfo | None:
        return self._inner.quota

    @property
    def last_source(self) -> str | None:
        return self._inner.last_source

    def session(self, year: int, gp: int | str, session: str) -> Session:
        return Session(self._loop, self._inner.session(year, gp, session))

    def event_schedule(self, year: int) -> pl.DataFrame:
        return self._loop.run(self._inner.event_schedule(year))

    def event(self, year: int, gp: int | str) -> dict[str, Any]:
        return self._loop.run(self._inner.event(year, gp))

    def event_sessions(self, year: int, gp: int | str) -> pl.DataFrame:
        return self._loop.run(self._inner.event_sessions(year, gp))

    def events_remaining(self, year: int, *, after: datetime | None = None) -> pl.DataFrame:
        return self._loop.run(self._inner.events_remaining(year, after=after))

    def driver_standings(self, year: int, round: int | None = None) -> pl.DataFrame:  # noqa: A002
        return self._loop.run(self._inner.driver_standings(year, round))

    def constructor_standings(
        self, year: int, round: int | None = None
    ) -> pl.DataFrame:  # noqa: A002
        return self._loop.run(self._inner.constructor_standings(year, round))

    def race_results(self, year: int, round: int) -> pl.DataFrame:  # noqa: A002
        return self._loop.run(self._inner.race_results(year, round))

    def circuit_info(self, circuit_id: int | str, *, year: int | None = None) -> CircuitInfo:
        return self._loop.run(self._inner.circuit_info(circuit_id, year=year))

    def circuits(self, year: int) -> list[dict[str, Any]]:
        return self._loop.run(self._inner.circuits(year))

    def close(self) -> None:
        self._loop.run(self._inner.aclose())
        self._loop.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


async def _make_async_client(
    api_key: str | None, config: ClientConfig | None, cache: CacheBackend | None
) -> AsyncClient:
    """Construct the async client inside the loop thread (binds httpx to that loop)."""
    return AsyncClient(api_key, config=config, cache=cache)
