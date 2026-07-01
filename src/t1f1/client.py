"""Client objects: the entry point that wires transports and sources together.

``AsyncClient`` is the async core; ``Client`` is a blocking facade. Passing an
``api_key`` enables the premium tier (analysis products served by ``api.t1f1.com``).
"""

from __future__ import annotations

import httpx

from t1f1._sync import LoopThread
from t1f1.config import ClientConfig
from t1f1.session import AsyncSession, Session
from t1f1.sources.raw_f1 import RawF1Source
from t1f1.sources.t1api import API_KEY_HEADER, T1APISource
from t1f1.transport import AsyncTransport


class AsyncClient:
    """Async F1 telemetry client.

    Parameters
    ----------
    api_key:
        When provided, analysis methods are served by ``api.t1f1.com``.
    config:
        Base URLs, timeouts, and retry policy.
    f1_client / t1api_client:
        Optionally inject ``httpx.AsyncClient`` instances (used by tests with
        ``httpx.MockTransport``). When injected, the caller owns their lifecycle.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        config: ClientConfig | None = None,
        f1_client: httpx.AsyncClient | None = None,
        t1api_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config or ClientConfig()
        self._api_key = api_key

        self._f1_transport = AsyncTransport(
            source="livetiming",
            config=self._config,
            base_headers=self._config.f1_headers,
            client=f1_client,
        )
        self._t1api_transport: AsyncTransport | None = None
        if api_key:
            self._t1api_transport = AsyncTransport(
                source="t1api",
                config=self._config,
                base_headers={API_KEY_HEADER: api_key},
                client=t1api_client,
            )

    @property
    def is_premium(self) -> bool:
        return self._t1api_transport is not None

    def session(self, year: int, gp: int | str, session: str) -> AsyncSession:
        """Build a session handle. Resolution/fetching happens lazily on first use."""
        raw = RawF1Source(self._f1_transport, self._config, year, gp, session)
        premium: T1APISource | None = None
        if self._t1api_transport is not None:
            premium = T1APISource(self._t1api_transport, self._config, year, gp, session, raw=raw)
        return AsyncSession(year, gp, session, raw=raw, premium=premium)

    async def aclose(self) -> None:
        await self._f1_transport.aclose()
        if self._t1api_transport is not None:
            await self._t1api_transport.aclose()

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()


class Client:
    """Blocking facade over :class:`AsyncClient`."""

    def __init__(self, api_key: str | None = None, *, config: ClientConfig | None = None) -> None:
        self._loop = LoopThread()
        self._inner = self._loop.run(_make_async_client(api_key, config))

    @property
    def is_premium(self) -> bool:
        return self._inner.is_premium

    def session(self, year: int, gp: int | str, session: str) -> Session:
        return Session(self._loop, self._inner.session(year, gp, session))

    def close(self) -> None:
        self._loop.run(self._inner.aclose())
        self._loop.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


async def _make_async_client(api_key: str | None, config: ClientConfig | None) -> AsyncClient:
    """Construct the async client inside the loop thread (binds httpx to that loop)."""
    return AsyncClient(api_key, config=config)
