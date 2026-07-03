"""Two-tier caching: raw HTTP response bytes + decoded polars frames.

Both tiers are optional and off by default. Unlike fastf1's ``Cache.enable_cache``
(global, process-wide mutable state), caching here is scoped per :class:`~t1f1.client.Client`
instance — safer for concurrent multi-session use (e.g. a web server juggling several
API keys/users) and easier to reason about in tests. ``enable_cache`` is a convenience
factory, not a global switch.

Disk-backed (:class:`DiskCache`) is the default backend. :class:`RedisCache` is
available for shared/team caches when the optional ``redis`` package is installed
(``pip install "t1f1-sdk[redis]"``).

Most cached data is an immutable historical archive — a completed session's feed
never changes — so the default ``ttl=None`` caches forever. Pass ``ttl`` (seconds) to
expire entries for data that can legitimately change under a stable URL (e.g. the
current season's ``Index.json`` gaining new rounds as they're published).
"""

from __future__ import annotations

import hashlib
import io
import json
import time
from pathlib import Path
from typing import Protocol, runtime_checkable

import polars as pl


@runtime_checkable
class CacheBackend(Protocol):
    """Pluggable cache storage. Implementations must be safe for concurrent use."""

    async def get_bytes(self, key: str) -> bytes | None: ...
    async def set_bytes(self, key: str, value: bytes) -> None: ...
    async def get_frame(self, key: str) -> pl.DataFrame | None: ...
    async def set_frame(self, key: str, frame: pl.DataFrame) -> None: ...
    async def aclose(self) -> None: ...


def _hash_key(key: str) -> str:
    """Filesystem/Redis-safe digest for an arbitrary cache key (a URL or frame key)."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class DiskCache:
    """Local-filesystem cache: raw HTTP bytes under ``http/``, decoded frames as
    parquet under ``frames/``. Both are content-addressed by a SHA-256 of the key, with
    a small JSON sidecar recording the original key and write time (for ``ttl`` checks
    and debuggability)."""

    def __init__(self, path: str | Path, *, ttl: float | None = None) -> None:
        self._root = Path(path)
        self._http_dir = self._root / "http"
        self._frames_dir = self._root / "frames"
        self._http_dir.mkdir(parents=True, exist_ok=True)
        self._frames_dir.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl

    def _fresh(self, meta_path: Path) -> bool:
        if self._ttl is None:
            return True
        if not meta_path.exists():
            return False
        try:
            cached_at = json.loads(meta_path.read_text())["cached_at"]
        except (OSError, ValueError, KeyError):
            return False
        return (time.time() - cached_at) < self._ttl

    @staticmethod
    def _write_meta(meta_path: Path, key: str) -> None:
        meta_path.write_text(json.dumps({"key": key, "cached_at": time.time()}))

    async def get_bytes(self, key: str) -> bytes | None:
        digest = _hash_key(key)
        blob_path = self._http_dir / f"{digest}.bin"
        meta_path = self._http_dir / f"{digest}.meta.json"
        if not blob_path.exists() or not self._fresh(meta_path):
            return None
        try:
            return blob_path.read_bytes()
        except OSError:
            return None

    async def set_bytes(self, key: str, value: bytes) -> None:
        digest = _hash_key(key)
        (self._http_dir / f"{digest}.bin").write_bytes(value)
        self._write_meta(self._http_dir / f"{digest}.meta.json", key)

    async def get_frame(self, key: str) -> pl.DataFrame | None:
        digest = _hash_key(key)
        frame_path = self._frames_dir / f"{digest}.parquet"
        meta_path = self._frames_dir / f"{digest}.meta.json"
        if not frame_path.exists() or not self._fresh(meta_path):
            return None
        try:
            return pl.read_parquet(frame_path)
        except (OSError, pl.exceptions.PolarsError):
            return None

    async def set_frame(self, key: str, frame: pl.DataFrame) -> None:
        digest = _hash_key(key)
        frame.write_parquet(self._frames_dir / f"{digest}.parquet")
        self._write_meta(self._frames_dir / f"{digest}.meta.json", key)

    def clear(self) -> None:
        """Remove every cached entry (both tiers). Synchronous — meant for ad hoc/test use."""
        for directory in (self._http_dir, self._frames_dir):
            for entry in directory.glob("*"):
                entry.unlink(missing_ok=True)

    async def aclose(self) -> None:
        pass  # no persistent connection to release


class RedisCache:
    """Shared/team cache backed by Redis. Requires the optional ``redis`` package.

    Raw bytes and parquet-serialized frames are both stored as Redis strings under
    ``{prefix}:http:{digest}`` / ``{prefix}:frame:{digest}``, with ``ttl`` (seconds)
    passed straight through to Redis ``EX`` if given.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        *,
        ttl: float | None = None,
        prefix: str = "t1f1",
    ) -> None:
        try:
            from redis import asyncio as redis_asyncio
        except ImportError as exc:  # pragma: no cover - exercised only without redis installed
            raise ImportError(
                "RedisCache requires the optional 'redis' package: pip install redis"
            ) from exc
        self._redis = redis_asyncio.from_url(url)
        self._ttl = int(self._round_up(ttl)) if ttl is not None else None
        self._prefix = prefix

    @staticmethod
    def _round_up(ttl: float) -> float:
        return ttl if ttl == int(ttl) else int(ttl) + 1

    def _http_key(self, key: str) -> str:
        return f"{self._prefix}:http:{_hash_key(key)}"

    def _frame_key(self, key: str) -> str:
        return f"{self._prefix}:frame:{_hash_key(key)}"

    async def get_bytes(self, key: str) -> bytes | None:
        return await self._redis.get(self._http_key(key))

    async def set_bytes(self, key: str, value: bytes) -> None:
        await self._redis.set(self._http_key(key), value, ex=self._ttl)

    async def get_frame(self, key: str) -> pl.DataFrame | None:
        blob = await self._redis.get(self._frame_key(key))
        if blob is None:
            return None
        return pl.read_parquet(io.BytesIO(blob))

    async def set_frame(self, key: str, frame: pl.DataFrame) -> None:
        buffer = io.BytesIO()
        frame.write_parquet(buffer)
        await self._redis.set(self._frame_key(key), buffer.getvalue(), ex=self._ttl)

    async def aclose(self) -> None:
        await self._redis.aclose()


def enable_cache(path: str | Path, *, ttl: float | None = None) -> DiskCache:
    """Convenience factory for the common case: ``Client(cache=enable_cache(path))``."""
    return DiskCache(path, ttl=ttl)
