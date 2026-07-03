# Contributing to t1f1-sdk

Thanks for considering a contribution — `t1f1-sdk` is built for the F1 community, and
fan-driven contributions (new analysis views, better docs, bug reports from a real
session you were working with) are exactly what makes it useful. This project is free
to use without an API key; the premium `api.t1f1.com` tier is optional.

## Dev setup

```bash
git clone https://github.com/Turn-One-Organization/t1f1-sdk.git
cd t1f1-sdk
pip install -e ".[dev,plot]"
```

`dev` pulls in test/lint tooling; `plot` pulls in `matplotlib` for the plotting
tutorials/examples.

## Before opening a PR

```bash
ruff check .
black --check .
pytest --cov=t1f1 --cov-report=term-missing
```

All three run in CI on every PR and must pass. If you touched ingestion/decode code,
also see `docs/concepts/data-shapes.md` — offline fixtures alone have missed real
feed-shape quirks before, so a manual smoke test against a live session
(`pytest -m live`) is worth doing if you can.

## PR titles must be Conventional Commits

We squash-merge PRs, and the **PR title** becomes the commit on `master` that drives
automatic versioning (`python-semantic-release`) and the PyPI release. CI will reject
a PR whose title doesn't follow this format:

```
<type>(<optional scope>): <description>

feat(analysis): add tyre-degradation regression
fix(ingestion): handle missing pit_out_time on long stints
docs(tutorials): add matplotlib track-dominance recipe
chore(ci): bump python-semantic-release
```

Common types: `feat` (new capability, minor version bump), `fix` (bug fix, patch
bump), `docs`, `chore`, `refactor`, `test`, `perf`. A breaking change bumps the major
version — add `!` after the type/scope (`feat!: ...`) or a `BREAKING CHANGE:` footer.

## Changelog

Add an entry under `## [Unreleased]` in `CHANGELOG.md` for any user-facing change
(new function, behavior change, bug fix). This file is hand-maintained (not
auto-generated) so it stays readable — group entries under `### Added` / `### Fixed`
/ `### Changed` / `### Removed` as appropriate.

## Code style

- No comments explaining *what* code does — names should do that. Comments are for
  non-obvious *why* (a workaround, an invariant, a subtle constraint).
- Reuse existing schemas/frame helpers (`t1f1.schemas`, `t1f1.frames`) instead of
  hand-rolling new DataFrame construction — see `docs/concepts/data-shapes.md`.
- Build decode frames with an explicit `schema=` rather than inferring from rows and
  casting after (see the `[0.2.0]` changelog entry for why — nullable columns can
  silently mis-infer on real sessions).

## Reporting bugs / requesting features

Use the issue templates — a bug report with the exact `year/gp/session` you were
loading is far easier to reproduce than a description alone.
