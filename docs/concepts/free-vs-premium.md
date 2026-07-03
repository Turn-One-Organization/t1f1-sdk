# Free vs Premium

`t1f1-sdk` supports both free and premium usage.

## Free

The free path uses the official F1 live-timing feed for raw session data and local computation
for the analysis that the SDK can derive on its own.

## Premium

If you pass an API key, the SDK can route supported analysis and metadata requests to
`api.t1f1.com`.

## Important routing rules

- `telemetry()` and other raw session accessors always use the free feed.
- Circuit metadata is premium-only.
- Some comparison methods use premium output only when no lap overrides are provided.
- Premium access is opportunistic: if the premium path fails with a retryable upstream
  error (an outage, rate limit, or "not published yet" response), the SDK silently
  falls back to local free-tier compute. An invalid/rejected API key does **not**
  trigger this fallback — that's a configuration mistake, and it's raised as
  `AuthError` rather than quietly masked as a degraded free-tier result.

## Inspecting which tier actually served a call

Every dual-tier `Session`/`AsyncSession` carries a `last_source` attribute
(`"t1api"` or `"free"`), updated after each analysis call:

```python
session.driver_pace()
print(session.last_source)  # "t1api" if premium served it, "free" if it fell back
```

`Client`/`AsyncClient` carries the same for `driver_standings()`/
`constructor_standings()` (`"t1api"` or `"ergast"`), plus a `quota` property exposing
the T1API rate-limit usage from its most recent response (`limit`/`remaining`/`reset`,
or `None` before any premium request has hit the network):

```python
client.driver_standings(2024)
print(client.quota)  # QuotaInfo(limit=300, remaining=299, reset=1700000000)
```

See [Session API](../api-reference/session.md) for the method list.