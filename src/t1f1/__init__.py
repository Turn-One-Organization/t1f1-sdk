"""t1f1 — a fast, polars-native Formula 1 telemetry SDK.

Free tier fetches raw data directly from the official F1 live-timing static feed.
Premium tier (with an ``api_key``) routes verified/enriched analysis products to
``api.t1f1.com``.

Quickstart
----------
>>> from t1f1 import Client
>>> session = Client().session(2024, "Monza", "Q")
>>> telemetry = session.telemetry("VER")  # polars DataFrame

Async users can drive the core directly:

>>> import asyncio
>>> from t1f1 import AsyncClient
>>> async def main():
...     session = AsyncClient().session(2024, "Monza", "Q")
...     return await session.telemetry("VER")
>>> df = asyncio.run(main())
"""

from t1f1._version import __version__
from t1f1.client import AsyncClient, Client
from t1f1.config import ClientConfig
from t1f1.exceptions import (
    AuthError,
    DataNotAvailableError,
    SessionNotFoundError,
    T1F1Error,
    UpstreamUnavailableError,
)

__all__ = [
    "AsyncClient",
    "Client",
    "ClientConfig",
    "T1F1Error",
    "AuthError",
    "DataNotAvailableError",
    "SessionNotFoundError",
    "UpstreamUnavailableError",
    "__version__",
]
