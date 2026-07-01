# t1f1-sdk

A fast, robust **Formula 1 telemetry SDK** — a modern, `polars`-native competitor to
[`fastf1`](https://github.com/theOehrly/Fast-F1).

`t1f1-sdk` uses a **hybrid architecture**:

- **Free tier (no API key):** fetches raw data directly from the official F1
  live-timing static feed (`livetiming.formula1.com`), decodes it, and returns
  [`polars`](https://pola.rs) DataFrames.
- **Premium tier (API key):** transparently routes cleaned/verified/enriched analysis
  products to our proprietary API at [`api.t1f1.com`](https://api.t1f1.com).

## Why t1f1 over fastf1

| | fastf1 | t1f1-sdk |
|---|---|---|
| DataFrame engine | pandas | **polars** (Arrow, multithreaded, lazy) |
| Network | sync, sequential | **async, concurrent** stream fetch |
| Cache | raw HTTP blobs | **parquet** decoded frames |
| Types | implicit `object` columns | **typed schemas**, explicit units |
| Data quality | raw feed as-is | **T1API-verified** data in premium |

## Install

```bash
pip install -e ".[dev]"   # from source, with dev tooling
```

Package name on pip: `t1f1-sdk`

Import name in Python: `t1f1`

If you prefer requirements files instead of editable installs:

```bash
pip install -r requirements-dev.txt   # full dev setup
# or
pip install -r requirements.txt       # runtime only
```

Requires Python 3.10+.

## Use

This is a Python library, so you use it from code rather than running a command-line
program.

```python
from t1f1 import Client

with Client() as client:
  session = client.session(2024, "Monza", "Q")
  telemetry = session.telemetry("VER")
  print(telemetry.head())
```

If you want the premium tier, pass your API key:

```python
from t1f1 import Client

with Client(api_key="YOUR_KEY") as client:
  session = client.session(2024, "Monza", "Q")
  print(session.top_speeds())
```

## Quickstart

```python
from t1f1 import Client

session = Client().session(2024, "Monza", "Q")
telemetry = session.telemetry("VER")   # polars DataFrame: speed_kmh, throttle, gear, ...
print(telemetry.head())

# Analysis: computed locally on the free tier, served by api.t1f1.com when keyed.
print(session.top_speeds())
```

### Premium tier

```python
from t1f1 import Client

session = Client(api_key="…").session(2024, "Monza", "Q")
session.telemetry("VER")   # still the raw feed (verified endpoints coming)
session.top_speeds()       # served by api.t1f1.com
```

### Async core

```python
import asyncio
from t1f1 import AsyncClient

async def main():
    session = AsyncClient().session(2024, "Monza", "Q")
    return await session.telemetry("VER")

df = asyncio.run(main())
```

## Status

Module 1 (hybrid foundation) is under active development. See the roadmap for the path
to full `fastf1` parity and beyond.

## License

MIT
