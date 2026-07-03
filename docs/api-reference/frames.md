# Frames API

`t1f1-sdk` avoids subclassing `polars.DataFrame` (polars discourages it). Instead
there are two patterns, depending on the use case:

1. **`LapsFrame`** — a thin composable wrapper with chainable `pick_*` filter
   *methods*, for the common "filter a laps table down" workflow.
2. **`t1f1.frames.telemetry`** — plain, pure *functions* over a
   `TELEMETRY_SCHEMA`-shaped `pl.DataFrame`, chainable via polars' native `.pipe()`.

Both patterns always give you `.to_polars()` / the frame itself for anything not
covered — no lock-in to the wrapper.

## `LapsFrame`

```python
from t1f1.frames.laps import LapsFrame
```

`session.laps()` already returns one; you only construct it directly if you're
wrapping a raw `pl.DataFrame` yourself (e.g. `LapsFrame(some_frame)`).

```python
laps = session.laps()          # LapsFrame
len(laps)                      # row count
laps.to_polars()                # -> pl.DataFrame, for anything not covered below
```

Every `pick_*` method returns a **new** `LapsFrame` (nothing is mutated), so calls chain:

```python
quick_ver_laps = (
    session.laps()
    .pick_drivers("VER")
    .pick_not_deleted()
    .pick_wo_box()
    .pick_quicklaps(threshold=1.05)
)
```

### Selection

| Method | Signature | Example |
|---|---|---|
| `pick_drivers` | `(*drivers: str) -> LapsFrame` | `laps.pick_drivers("VER", "NOR")` |
| `pick_teams` | `(*teams: str) -> LapsFrame` | `laps.pick_teams("Red Bull", "Mclaren")` (case-insensitive) |
| `pick_compounds` | `(*compounds: str) -> LapsFrame` | `laps.pick_compounds("SOFT")` |
| `pick_laps` | `(lap_numbers: int \| list[int]) -> LapsFrame` | `laps.pick_laps([1, 2, 3])` or `laps.pick_laps(5)` |
| `pick_track_status` | `(status: str) -> LapsFrame` | `laps.pick_track_status("2")` (yellow-flag laps) |

### Quality filters

| Method | Signature | Example |
|---|---|---|
| `pick_not_deleted` | `() -> LapsFrame` | `laps.pick_not_deleted()` |
| `pick_accurate` | `() -> LapsFrame` | `laps.pick_accurate()` |
| `pick_wo_box` | `() -> LapsFrame` | `laps.pick_wo_box()` — excludes in/out laps |
| `pick_box_laps` | `() -> LapsFrame` | `laps.pick_box_laps()` — only in/out laps |
| `pick_quicklaps` | `(threshold: float = 1.07) -> LapsFrame` | `laps.pick_quicklaps(1.05)` — laps within `threshold` x the frame's fastest (107%-rule by default) |
| `pick_fastest` | `() -> LapsFrame` | `laps.pick_drivers("VER").pick_fastest()` — the single fastest lap |

### Grouping / iteration

| Method | Signature | Example |
|---|---|---|
| `split_qualifying_sessions` | `() -> list[LapsFrame]` | `q1, q2, q3 = session.laps().split_qualifying_sessions()` (returns `[self]` if no `qualifying_segment` column is present) |
| `iterlaps` | `() -> Iterator[dict]` | `for lap in laps.iterlaps(): print(lap["lap_number"], lap["lap_time"])` |

## `t1f1.frames.telemetry` — pure transform functions

```python
from t1f1.frames.telemetry import (
    add_distance, add_differential_distance, add_relative_distance,
    add_track_status, merge_channels, slice_by_time, slice_by_mask,
    resample_channels, fill_missing, compute_driver_ahead,
)
```

Every function takes a `pl.DataFrame` and returns a new one — never mutates the
input. Chain with `.pipe()`:

```python
tel = (
    session.telemetry("VER")
    .pipe(slice_by_time, start=lap_start, end=lap_end)
    .pipe(add_distance)
    .pipe(add_relative_distance)
)
```

| Function | Signature | Purpose |
|---|---|---|
| `add_distance` | `(df) -> pl.DataFrame` | (Re)compute cumulative `distance` (m) from `speed_kmh` x dt. Needed again after slicing/resampling changes the sample grid. |
| `add_differential_distance` | `(df) -> pl.DataFrame` | Adds `differential_distance`: per-sample distance delta. |
| `add_relative_distance` | `(df) -> pl.DataFrame` | Adds `relative_distance`: `distance` normalized to `0..1`. |
| `add_track_status` | `(df, track_status) -> pl.DataFrame` | Stamps each sample's `track_status` via nearest-before join on `timestamp`. |
| `merge_channels` | `(df, other, *, on="timestamp") -> pl.DataFrame` | Merge another frame's columns on by nearest match (e.g. weather onto telemetry). Overlapping column names get suffixed `_right`. |
| `slice_by_time` | `(df, start, end) -> pl.DataFrame` | Keep `start <= timestamp <= end`. |
| `slice_by_mask` | `(df, mask: pl.Series) -> pl.DataFrame` | Keep rows where a boolean mask is true. |
| `resample_channels` | `(df, every="100ms") -> pl.DataFrame` | Resample onto a fixed-frequency grid — float channels averaged per bucket, discrete channels (gear, DRS, ...) take the bucket's latest value. |
| `fill_missing` | `(df) -> pl.DataFrame` | Forward-fill then back-fill every non-identity column. |
| `compute_driver_ahead` | `(target, others: dict[str, pl.DataFrame]) -> pl.DataFrame` | Adds `driver_ahead`/`distance_to_driver_ahead`, comparing `target` against every driver in `others` (TLA -> telemetry). Powers `session.driver_ahead()`. |

```python
# Merge weather onto telemetry
tel_with_weather = merge_channels(session.telemetry("VER"), session.weather())

# Resample to 1-second buckets before plotting a long stint
smoothed = resample_channels(session.telemetry("VER"), every="1s")

# Fill gaps in a slice that has intermittent nulls
clean = fill_missing(some_slice)
```

## `t1f1.utils.delta_time`

```python
from t1f1.utils import delta_time

delta_time(reference: pl.DataFrame, comparison: pl.DataFrame) -> pl.DataFrame
```

Distance-aligned time delta between two laps' telemetry. Returns one row per
`reference` sample: `distance` (reference's distance grid) and `delta_seconds`
(**positive = `comparison` is behind at that point on track**). Both frames need
`timestamp` and `distance` columns — call `add_distance` first if slicing changed
the sample grid. This is what `session.compare()`/`analysis.compare()` use
internally; call it directly if you only need the delta trace.

```python
ver_lap = session.lap_telemetry("VER", 12)
nor_lap = session.lap_telemetry("NOR", 12)
delta = delta_time(ver_lap, nor_lap)
print(delta.select("distance", "delta_seconds"))
```
