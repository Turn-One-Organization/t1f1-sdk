# Errors

Every error the SDK raises is a subclass of `t1f1.T1F1Error` (itself an `Exception`).
All of the concrete classes below are importable straight from the `t1f1` package.

```python
from t1f1 import (
    T1F1Error,
    AuthError,
    RateLimitError,
    SessionNotFoundError,
    DataNotAvailableError,
    UpstreamUnavailableError,
)
```

## `T1F1Error`

Base class for everything below. Catch this alone if you just want "something went
wrong talking to F1 data sources" without distinguishing why.

```python
try:
    session = client.session(2024, "Monza", "Q")
    laps = session.laps()
except T1F1Error as exc:
    print(f"couldn't load data: {exc}")
```

## `AuthError`

The T1API key was missing/rejected (HTTP 401/403), or a premium-only method
(`circuit_info`, `circuits`) was called without a key at all.

**Never silently swallowed by the fallback logic** — see
[Free vs Premium](../concepts/free-vs-premium.md). A dual-tier method that gets an
`AuthError` from premium raises it immediately rather than degrading to the free
tier, since a bad key is a configuration mistake you should see, not something
papered over as "the SDK just used the free tier instead."

```python
from t1f1 import Client, AuthError

with Client() as free_client:
    try:
        free_client.circuit_info("monza")
    except AuthError:
        print("circuit_info needs an api_key")
```

## `RateLimitError`

T1API rate limit exceeded (HTTP 429).

```python
attrs = ["retry_after"]  # float | None — seconds to wait, if the server sent Retry-After
```

```python
from t1f1 import RateLimitError

try:
    client.driver_standings(2024)
except RateLimitError as exc:
    print(f"rate limited, retry after {exc.retry_after}s")
```

In practice you'll rarely need to catch this directly on dual-tier methods (`session
.driver_pace()`, `client.driver_standings()`, ...) — they already catch it
internally and fall back to the free tier automatically. It's only visible if you're
calling the premium source in a context with no fallback (or if the fallback itself
also fails).

## `SessionNotFoundError`

The requested `(year, gp, session)` doesn't resolve to anything in the schedule.
Carries lookup hints so you can suggest corrections without a second round trip.

```python
attrs = ["year", "gp", "session", "reason", "valid_rounds", "suggestions"]
```

```python
from t1f1 import SessionNotFoundError

try:
    session = client.session(2024, 99, "Q")
except SessionNotFoundError as exc:
    print(exc.reason)
    print("valid rounds:", exc.valid_rounds)
    print("did you mean:", exc.suggestions)
```

## `DataNotAvailableError`

The session is real and scheduled, but no source has the data yet (a session that
just finished, before the feed has fully published). Retryable — `retry_after`
defaults to 300 seconds.

```python
attrs = ["year", "gp", "session", "sources_tried", "retry_after"]
```

```python
from t1f1 import DataNotAvailableError
import time

try:
    laps = session.laps()
except DataNotAvailableError as exc:
    time.sleep(exc.retry_after)
    laps = session.laps()  # retry
```

## `UpstreamUnavailableError`

An upstream (F1 live-timing, T1API, or Ergast) actively failed — a 5xx response or a
network error. Retryable, shorter default window (`retry_after` defaults to 60
seconds) than `DataNotAvailableError`.

```python
attrs = ["source", "reason", "retry_after"]  # source: "livetiming" | "t1api" | "ergast"
```

```python
from t1f1 import UpstreamUnavailableError

try:
    laps = session.laps()
except UpstreamUnavailableError as exc:
    print(f"{exc.source} is down: {exc.reason}, retry after {exc.retry_after}s")
```

## Retry guidance

| Error | Retry? | How |
|---|---|---|
| `DataNotAvailableError` | Yes | After `retry_after` (default 300s) — data is expected to appear |
| `UpstreamUnavailableError` | Yes | After `retry_after` (default 60s) — transient upstream failure |
| `RateLimitError` | Yes | After `retry_after` if given, otherwise back off |
| `SessionNotFoundError` | No | Fix the request — use `valid_rounds`/`suggestions` |
| `AuthError` | No | Fix the API key or config, not a retry situation |

The built-in `AsyncTransport` already retries transient 429/503/5xx responses with
backoff internally before any of the above ever reaches your code (see
[Configuration](../reference/configuration.md) for `max_retries`/`backoff_base`) —
these exceptions mean the retry budget was exhausted, not "the very first attempt
failed."
