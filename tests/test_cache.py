"""Cache backends in isolation: disk (persistent) and Redis (optional) tiers."""

from __future__ import annotations

import time

import polars as pl

from t1f1.cache import DiskCache, RedisCache, enable_cache


async def test_disk_cache_bytes_round_trip(tmp_path):
    cache = DiskCache(tmp_path)
    assert await cache.get_bytes("http://x/y") is None
    await cache.set_bytes("http://x/y", b"hello")
    assert await cache.get_bytes("http://x/y") == b"hello"


async def test_disk_cache_frame_round_trip(tmp_path):
    cache = DiskCache(tmp_path)
    frame = pl.DataFrame({"a": [1, 2, 3]})
    assert await cache.get_frame("laps") is None
    await cache.set_frame("laps", frame)
    result = await cache.get_frame("laps")
    assert result is not None
    assert result.equals(frame)


async def test_disk_cache_ttl_expiry(tmp_path, monkeypatch):
    cache = DiskCache(tmp_path, ttl=10)
    await cache.set_bytes("k", b"v")
    assert await cache.get_bytes("k") == b"v"
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + 20)
    assert await cache.get_bytes("k") is None


async def test_disk_cache_no_ttl_never_expires(tmp_path, monkeypatch):
    cache = DiskCache(tmp_path)
    await cache.set_bytes("k", b"v")
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + 10_000_000)
    assert await cache.get_bytes("k") == b"v"


async def test_disk_cache_clear(tmp_path):
    cache = DiskCache(tmp_path)
    await cache.set_bytes("k", b"v")
    cache.clear()
    assert await cache.get_bytes("k") is None


def test_enable_cache_returns_disk_cache(tmp_path):
    cache = enable_cache(tmp_path)
    assert isinstance(cache, DiskCache)


async def test_redis_cache_key_prefix_and_frame_serialization(monkeypatch):
    store: dict[str, bytes] = {}

    class FakeRedis:
        async def get(self, key):
            return store.get(key)

        async def set(self, key, value, ex=None):
            store[key] = value

        async def aclose(self):
            pass

    import redis.asyncio as redis_asyncio

    monkeypatch.setattr(redis_asyncio, "from_url", lambda url: FakeRedis())

    cache = RedisCache("redis://fake", ttl=5.5, prefix="test")
    await cache.set_bytes("k1", b"v1")
    assert await cache.get_bytes("k1") == b"v1"
    assert next(iter(store)).startswith("test:http:")

    frame = pl.DataFrame({"x": [1, 2]})
    await cache.set_frame("laps", frame)
    result = await cache.get_frame("laps")
    assert result is not None
    assert result.equals(frame)

    await cache.aclose()
