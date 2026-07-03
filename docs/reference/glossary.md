# Glossary

- `Client`: blocking top-level SDK entrypoint.
- `AsyncClient`: async top-level SDK entrypoint.
- `Session`: blocking session handle.
- `AsyncSession`: async session handle.
- `gp`: Grand Prix identifier used to resolve a session — round number, event key, or
  fuzzy name/location (see [Events API](../api-reference/events.md#a-note-on-round-numbers)
  for why fuzzy names are safer on older seasons).
- `session`: session code such as `Q` or `R`.
- `premium`: any feature that uses `api.t1f1.com`.
- `raw telemetry`: data fetched directly from the live-timing feed.
- `analysis`: derived tables such as pace, comparison, and stint summaries.
- `LapsFrame`: the chainable wrapper `session.laps()` returns — see [Frames API](../api-reference/frames.md).
- `cache`: optional two-tier (HTTP bytes + decoded frames) storage passed as `cache=` to a client — see [Caching](../concepts/caching.md).
- `last_source`: which tier (`"t1api"`/`"free"`/`"ergast"`) actually served the most recent dual-tier call.
- `quota`: T1API's rate-limit usage from its most recent response, exposed via `Client.quota`.
- `fallback`: a dual-tier method degrading from premium to free-tier compute after a retryable upstream error — never on a rejected API key.