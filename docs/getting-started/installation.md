# Installation

`t1f1-sdk` requires Python 3.10 or newer.

## Install from source

```bash
pip install -e ".[dev]"
```

## Install from requirements files

```bash
pip install -r requirements-dev.txt
```

For runtime-only installs:

```bash
pip install -r requirements.txt
```

## Dependencies

The runtime dependencies are:

- `httpx` for transport.
- `polars` for returned data frames.
- `numpy` for numerical helpers.
- `tzdata` on Windows so UTC timestamps resolve correctly.

### Optional: Redis cache backend

```bash
pip install "t1f1-sdk[redis]"
```

Only needed if you use `t1f1.cache.RedisCache` — see [Caching](../concepts/caching.md).
The default `DiskCache` backend needs no extra dependency.

## Next step

After installation, read [Authentication](authentication.md) and then [Quickstart](quickstart.md).