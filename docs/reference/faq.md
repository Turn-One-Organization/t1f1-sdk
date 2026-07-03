# FAQ

## Why does telemetry work without an API key?

Raw session telemetry comes from the free F1 feed and does not require premium access.

## Why do some methods require premium access?

Some methods return curated or enriched data that is only available through `api.t1f1.com`.

## Why is the SDK using polars?

The SDK is built around `polars` to keep results fast, typed, and easy to compose.

## Where should I start?

Start with [Quickstart](../getting-started/quickstart.md) and then move to the [Client API](../api-reference/client.md).

## How do I know what columns a method returns?

Every returned frame has a fixed, documented schema — see [Schemas](../api-reference/schemas.md)
for a complete data dictionary, or just call `.schema` on any frame you get back.

## I'm coming from fastf1 — where's the cheatsheet?

[Migrating from fastf1](../getting-started/migration-from-fastf1.md) maps common
fastf1 calls (and pandas idioms) onto their `t1f1-sdk` equivalents.

## Does the SDK retry failed requests automatically?

Yes — `AsyncTransport` retries 429/503/5xx responses and network errors with
backoff before raising (see [Configuration](configuration.md) for `max_retries`/
`backoff_base`). Dual-tier methods (premium analysis, standings) additionally fall
back from T1API to the free tier / Ergast on a retryable error — see
[Free vs Premium](../concepts/free-vs-premium.md).

## Can I cache results between runs?

Yes — pass `cache=enable_cache("./.t1f1_cache")` to `Client`/`AsyncClient`. See
[Caching](../concepts/caching.md).

## Why is `client.session(2024, 1, "Q")` giving me the wrong Grand Prix?

Some past seasons' `Index.json` don't list every round, so an integer round number
can resolve positionally to the wrong event. Use the event name instead — see the
[Events API](../api-reference/events.md#a-note-on-round-numbers) note.