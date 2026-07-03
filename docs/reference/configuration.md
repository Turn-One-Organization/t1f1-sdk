# Configuration

```python
from t1f1 import Client, ClientConfig
```

`ClientConfig` is an immutable (`frozen=True`) dataclass shared across a client and
all of its transports (F1 feed, T1API, Ergast).

## Fields

| Field | Default | Meaning |
|---|---|---|
| `f1_base_url` | `"https://livetiming.formula1.com/static/"` | F1 live-timing CDN. Point at a proxy (e.g. a Cloudflare Worker mirror) if needed. |
| `t1api_base_url` | `"https://api.t1f1.com"` | T1API premium base. |
| `ergast_base_url` | `"https://api.jolpi.ca/ergast/f1/"` | jolpica-f1's free, public Ergast-compatible API. |
| `timeout` | `30.0` | Per-request timeout, seconds. |
| `max_retries` | `3` | Retries on a 429/503/5xx response or network error before raising. |
| `backoff_base` | `0.5` | Base seconds for exponential backoff between retries (with jitter). |
| `max_retry_after` | `10.0` | Cap on how long a server-provided `Retry-After` header is honored before giving up on that attempt. |
| `f1_headers` | browser-like `User-Agent`/`Accept`/`Origin`/`Referer` | Headers sent on every F1-feed request — required to avoid being blocked by the CDN. |

## Methods

| Method | Signature | Purpose |
|---|---|---|
| `f1_url` | `(path: str) -> str` | Join a path onto `f1_base_url`. |
| `t1api_url` | `(path: str) -> str` | Join a path onto `t1api_base_url`. |
| `ergast_url` | `(path: str) -> str` | Join a path onto `ergast_base_url`. |

## Usage

```python
from t1f1 import Client, ClientConfig

# Defaults
client = Client(config=ClientConfig())

# Custom retry policy / timeout
config = ClientConfig(timeout=60.0, max_retries=5, backoff_base=1.0)
client = Client(config=config)

# Point the F1 feed at a proxy
config = ClientConfig(f1_base_url="https://my-proxy.example.com/f1-mirror/")
client = Client(config=config)
```

Since `ClientConfig` is a frozen dataclass, "modifying" one means building a new
instance — use `dataclasses.replace` if you only want to override one field:

```python
from dataclasses import replace

base = ClientConfig()
slower = replace(base, timeout=90.0)
```

For caching (a separate, non-`ClientConfig` concept — passed as `cache=` directly
to `Client`/`AsyncClient`), see [Caching](../concepts/caching.md) and the
[Cache API](../api-reference/cache.md).