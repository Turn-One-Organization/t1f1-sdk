# Authentication

`t1f1-sdk` works in two modes.

## Free mode

If you do not pass an API key, the SDK uses the free F1 live-timing feed for raw session data
and local computation for the analysis methods that are available without premium access.

```python
from t1f1 import Client

client = Client()
```

## Premium mode

If you pass an API key, the SDK enables premium routing for supported analysis endpoints and
metadata helpers.

```python
from t1f1 import Client

client = Client(api_key="YOUR_API_KEY")
```

## What changes with an API key

- Some analysis methods are served by `api.t1f1.com` when available.
- Circuit information and circuit lists require premium access.
- Free-tier raw telemetry still comes from the live-timing feed.

## Recommendation

Start without an API key to learn the public API. Add one later if you need premium analysis
or circuit metadata.