"""Async HTTP transport built on ``httpx.AsyncClient``.

One pooled client per transport, browser-like headers, UTF-8-BOM-aware decoding,
bounded retry that honours ``Retry-After``, and a status-code -> exception mapping
that mirrors the backend's error taxonomy.

Callers fetch several streams concurrently with :func:`asyncio.gather`; a single
transport (and its connection pool) is safe to share across those concurrent calls.
"""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any

import httpx

from t1f1.config import ClientConfig
from t1f1.exceptions import (
    AuthError,
    DataNotAvailableError,
    RateLimitError,
    SessionNotFoundError,
    UpstreamUnavailableError,
)


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header. Only the integer-seconds form is supported."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None  # HTTP-date form: fall back to our own backoff schedule.


class AsyncTransport:
    """A thin async HTTP wrapper scoped to a single upstream (``source``).

    Parameters
    ----------
    source:
        Label for the upstream (``"livetiming"`` or ``"t1api"``) used in error
        messages and to shape exception mapping.
    base_headers:
        Default headers sent with every request (F1 browser headers, or the T1API
        ``X-API-Key`` header).
    client:
        Optionally inject an ``httpx.AsyncClient`` (used by tests via
        ``httpx.MockTransport``). When injected, the caller owns its lifecycle.
    """

    def __init__(
        self,
        *,
        source: str,
        config: ClientConfig,
        base_headers: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._source = source
        self._config = config
        self._headers = dict(base_headers or {})
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.AsyncClient(
                headers=self._headers,
                timeout=config.timeout,
                follow_redirects=True,
            )
            self._owns_client = True

    async def __aenter__(self) -> AsyncTransport:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # -- public fetch helpers -------------------------------------------------

    async def get_bytes(self, url: str) -> bytes:
        response = await self._request(url)
        return response.content

    async def get_text(self, url: str) -> str:
        """Fetch and decode as UTF-8, tolerating the BOM the F1 CDN emits."""
        return (await self.get_bytes(url)).decode("utf-8-sig")

    async def get_json(self, url: str) -> Any:
        return json.loads(await self.get_text(url))

    # -- internals ------------------------------------------------------------

    async def _request(self, url: str) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                response = await self._client.get(url, headers=self._headers)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt >= self._config.max_retries:
                    raise UpstreamUnavailableError(
                        source=self._source, reason=f"Network error fetching {url}: {exc}"
                    ) from exc
                await self._sleep_backoff(attempt)
                continue

            if response.status_code < 400:
                return response

            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            if self._should_retry(response.status_code) and attempt < self._config.max_retries:
                await self._sleep_backoff(attempt, retry_after)
                continue

            self._raise_for_status(url, response, retry_after)

        # Exhausted retries on a retryable status/network error.
        raise UpstreamUnavailableError(
            source=self._source, reason=f"Failed to fetch {url}: {last_exc}"
        )

    @staticmethod
    def _should_retry(status_code: int) -> bool:
        return status_code in (429, 503) or 500 <= status_code < 600

    async def _sleep_backoff(self, attempt: int, retry_after: float | None = None) -> None:
        if retry_after is not None:
            delay = min(retry_after, self._config.max_retry_after)
        else:
            delay = self._config.backoff_base * (2**attempt)
            delay += random.uniform(0, self._config.backoff_base)  # noqa: S311 (jitter, not crypto)
        await asyncio.sleep(delay)

    def _raise_for_status(
        self, url: str, response: httpx.Response, retry_after: float | None
    ) -> None:
        status = response.status_code
        error_code, detail = self._read_error_body(response)

        if status in (401, 403):
            raise AuthError(detail or f"Authentication failed for {url} ({status})")
        if status == 404:
            raise SessionNotFoundError(reason=detail or f"Not found: {url}")
        if status == 429:
            raise RateLimitError(detail or "Rate limit exceeded", retry_after=retry_after)
        if status == 503:
            if error_code == "upstream_unavailable":
                raise UpstreamUnavailableError(
                    source=self._source, reason=detail, retry_after=retry_after
                )
            raise DataNotAvailableError(detail or "Data not available yet", retry_after=retry_after)
        if status >= 500:
            raise UpstreamUnavailableError(
                source=self._source,
                reason=detail or f"{self._source} returned {status} for {url}",
                retry_after=retry_after,
            )
        raise UpstreamUnavailableError(
            source=self._source, reason=detail or f"{self._source} returned {status} for {url}"
        )

    @staticmethod
    def _read_error_body(response: httpx.Response) -> tuple[str | None, str | None]:
        """Extract ``(error_code, detail)`` from a T1API-style JSON error body."""
        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError):
            return None, None
        if not isinstance(body, dict):
            return None, None
        return body.get("error"), body.get("detail")
