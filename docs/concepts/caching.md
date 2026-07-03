# Caching

`t1f1-sdk` caches at two levels, both optional and off by default:

1. **HTTP byte cache** — raw response bytes, keyed by URL. Covers every stream the
   SDK fetches (F1 feed, T1API, Ergast) automatically, with no per-source code needed.
2. **Decoded frame cache** — fully-decoded `polars` frames for `telemetry()`,
   `laps()`, `results()`, and `weather()`, keyed by the resolved session's directory.
   A hit here skips the network *and* re-parsing/re-decoding — the closest thing to
   fastf1's pickled-session cache, and the tier that actually delivers a fast warm
   reload.

```python
from t1f1 import Client
from t1f1.cache import enable_cache

client = Client(cache=enable_cache("./t1f1-cache"))
session = client.session(2024, "Monza", "Q")
session.laps()  # cold: fetches + decodes
```

Run the same code again (even in a fresh process) against the same cache directory
and `laps()` returns straight from disk.

## Scoped, not global

Unlike fastf1's `Cache.enable_cache(path)` (global, process-wide, mutable),
`t1f1-sdk`'s cache is passed explicitly to a `Client`/`AsyncClient`. This is a
deliberate deviation: a global cache is a footgun for anything juggling multiple API
keys or users in one process (a web server, a notebook switching between free and
premium clients) — scoping it per-client avoids that entirely.

## Backends

- `DiskCache` (default) — local filesystem, content-addressed by a hash of the key.
  Most cached data is an immutable historical archive (a completed session's feed
  never changes), so entries never expire unless you pass `ttl=`.
- `RedisCache` — for a shared/team cache. Requires the optional `redis` package
  (`pip install "t1f1-sdk[redis]"`).

```python
from t1f1.cache import RedisCache

client = Client(cache=RedisCache("redis://localhost:6379/0", ttl=3600))
```

## Measured effect

Live-tested against a real Qualifying session (laps + results + weather +
telemetry): a cold fetch took ~3.5s; a warm re-run against the same disk cache, with
entirely fresh `Client`/session objects, took ~0.5s — roughly 7x faster, with
byte-identical output. The dominant cost for a session this size is network + zlib
inflate, not `polars` decoding, so the cache (skipping the network round trip
entirely) is what actually moves the needle.
