# Cache API

```python
from t1f1.cache import enable_cache, DiskCache, RedisCache, CacheBackend
```

See [Caching](../concepts/caching.md) for the design (two tiers, why it's scoped
per-client rather than global). This page is the method-by-method reference.

## `enable_cache(path: str | Path, *, ttl: float | None = None) -> DiskCache`

Convenience factory for the common case.

```python
from t1f1 import Client
from t1f1.cache import enable_cache

client = Client(cache=enable_cache("./.t1f1_cache"))
```

## `DiskCache`

```python
DiskCache(path: str | Path, *, ttl: float | None = None)
```

Local-filesystem cache: raw HTTP bytes under `<path>/http/`, decoded parquet frames
under `<path>/frames/`, both content-addressed by a SHA-256 of the cache key.
`ttl=None` (default) never expires entries — most cached data is an immutable
historical archive (a completed session's feed never changes). Pass `ttl` (seconds)
for data that can legitimately change under a stable URL (e.g. the current season's
`Index.json` gaining new rounds as they're published):

```python
from t1f1.cache import DiskCache

cache = DiskCache("./.t1f1_cache")                      # never expires
cache = DiskCache("./.t1f1_cache", ttl=3600)             # expires after 1 hour
client = Client(cache=cache)
```

### Methods

All are `async` (the sync `Client` never calls them directly — they're invoked
internally by `AsyncTransport`/`RawF1Source`). You'd normally never call these
yourself; they're documented here for completeness / building a custom backend.

| Method | Signature |
|---|---|
| `get_bytes` | `async (key: str) -> bytes \| None` |
| `set_bytes` | `async (key: str, value: bytes) -> None` |
| `get_frame` | `async (key: str) -> pl.DataFrame \| None` |
| `set_frame` | `async (key: str, frame: pl.DataFrame) -> None` |
| `aclose` | `async () -> None` — no-op for `DiskCache` (no persistent connection) |

### `clear() -> None`

The one **synchronous** method — removes every cached entry (both tiers). Meant for
ad hoc/test use, e.g. clearing a stale cache between runs:

```python
cache = DiskCache("./.t1f1_cache")
cache.clear()
```

## `RedisCache`

```python
RedisCache(
    url: str = "redis://localhost:6379/0",
    *,
    ttl: float | None = None,
    prefix: str = "t1f1",
)
```

For a shared/team cache. Requires the optional `redis` package
(`pip install "t1f1-sdk[redis]"`) — raises `ImportError` with that install hint if
`redis` isn't installed. Same method surface as `DiskCache` (`get_bytes`,
`set_bytes`, `get_frame`, `set_frame`, `aclose`), backed by Redis strings under
`{prefix}:http:{digest}` / `{prefix}:frame:{digest}`.

```python
from t1f1.cache import RedisCache

cache = RedisCache("redis://localhost:6379/0", ttl=3600, prefix="myapp")
client = Client(cache=cache)
```

`aclose()` actually closes the Redis connection here (unlike `DiskCache`'s no-op) —
make sure you're using `Client`/`AsyncClient` as a context manager, or call
`client.close()`/`await client.aclose()` explicitly, so the connection doesn't leak.

## `CacheBackend` (protocol) — writing a custom backend

```python
from typing import Protocol
import polars as pl

class CacheBackend(Protocol):
    async def get_bytes(self, key: str) -> bytes | None: ...
    async def set_bytes(self, key: str, value: bytes) -> None: ...
    async def get_frame(self, key: str) -> pl.DataFrame | None: ...
    async def set_frame(self, key: str, frame: pl.DataFrame) -> None: ...
    async def aclose(self) -> None: ...
```

Any object implementing these five async methods works as `cache=` on
`Client`/`AsyncClient` — structural typing, no need to subclass anything.

## `QuotaInfo`

```python
from t1f1.transport import QuotaInfo
```

Not part of the cache module itself, but closely related to premium usage tracking
— see `Client.quota` on the [Client API](client.md#properties) page. A frozen
dataclass: `limit: int | None`, `remaining: int | None`, `reset: int | None`
(Unix timestamp of the next rate-limit window).
