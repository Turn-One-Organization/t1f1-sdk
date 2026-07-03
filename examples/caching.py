"""Two-tier caching: a warm reload skips both the network and re-decoding.

Run this twice — the second run should be noticeably faster once the disk cache is
populated (see docs/concepts/caching.md for the measured numbers).
"""

import time

from t1f1 import Client
from t1f1.cache import enable_cache

cache = enable_cache("./.t1f1_cache")

with Client(cache=cache) as client:
    t0 = time.perf_counter()
    session = client.session(2024, "Monza", "Q")
    laps = session.laps()
    telemetry = session.telemetry("VER")
    elapsed = time.perf_counter() - t0

print(f"laps={laps.to_polars().height} telemetry={telemetry.height} rows in {elapsed:.2f}s")
