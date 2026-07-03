# Changelog

`t1f1-sdk` follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

- **MAJOR** — breaking changes to public method signatures, schemas, or return types.
- **MINOR** — new methods, new optional parameters, new modules — backwards compatible.
- **PATCH** — bug fixes, doc/dependency updates, no public API change.

While the version stays `0.x`, minor releases may still include breaking changes as
the API settles; each one will be called out explicitly below.

## [Unreleased]

## [0.2.0] - 2026-07-03

### Fixed
- `decode_laps` (and every other `list[dict] -> pl.DataFrame` decode path) could
  raise `ComputeError` on real sessions where a nullable column (e.g.
  `pit_out_time`) stayed `null` past polars' schema-inference sample window and
  then received a real value later — typical on a long green-flag stint before the
  first pit stop. Fixed by constructing frames with an explicit `schema=` instead of
  inferring from the raw rows and casting afterward.

### Added
- Two-tier caching (`t1f1.cache`): raw HTTP byte cache + decoded-frame cache, `Disk`
  and `Redis` backends, scoped per `Client`/`AsyncClient` instance.
- Premium ergonomics: dual-tier analysis methods gracefully fall back to free-tier
  local compute on a retryable premium error (not on a rejected API key);
  `Session.last_source` / `Client.last_source` expose which tier actually served the
  last call; `Client.quota` surfaces T1API's `X-RateLimit-*` usage.
- `examples/` — runnable scripts for the free tier, caching, premium + fallback,
  concurrent multi-session loading, and matplotlib plotting recipes
  (`examples/plotting_matplotlib.py`, new optional `t1f1-sdk[plot]` extra).
- `docs/getting-started/migration-from-fastf1.md` — a fastf1 → t1f1 cheatsheet.
- `docs/concepts/caching.md`.
- `docs/tutorials/matplotlib-plots.md` — race pace, tyre stints, and speed-trace
  comparison charts on real session data, dark broadcast-style theme.
- CI: `.github/workflows/ci.yml` runs ruff, black, and the test suite (with a
  coverage gate) on every push/PR, across Python 3.10 and 3.12; PR titles are
  checked against Conventional Commits.
- `.github/workflows/release.yml`: automatic version bump (Conventional Commits via
  `python-semantic-release`), GitHub Release, and PyPI publish (trusted
  publishing/OIDC) on every push to `main`/`master` that warrants a release.
- `CONTRIBUTING.md`, issue/PR templates, and `LICENSE` (MIT) for external
  contributors.

### Changed
- `t1f1.plotting.TEAM_COLORS` updated to the 2026 grid (`Audi`, `Cadillac`,
  `Racing Bulls` replace the retired `Kick Sauber`/`RB` entries) — teams that
  rebrand/enter mid-generation would otherwise silently fall back to
  `FALLBACK_COLOR` (gray).

### Removed
- `sources/base.py`'s `DataSource` Protocol — dead code from the Module 1 scaffold,
  never imported anywhere.

## [0.1.0]

Initial release: hybrid free (F1 live-timing feed) / premium (`api.t1f1.com`)
architecture, session/laps/results/weather/telemetry, events/standings/circuits, the
analysis + plotting suite.
