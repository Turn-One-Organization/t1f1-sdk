"""Vectorized, composable transforms over a ``TELEMETRY_SCHEMA``-shaped frame.

Plain functions over a plain ``pl.DataFrame`` — chainable via ``.pipe()`` — rather
than a bespoke ``Telemetry`` subclass (fastf1's approach). Every function is pure: it
returns a new frame and never mutates its input.
"""

from __future__ import annotations

import numpy as np
import polars as pl

_KMH_TO_MS = 1000.0 / 3600.0


def add_distance(df: pl.DataFrame) -> pl.DataFrame:
    """(Re)compute cumulative ``distance`` (m) from ``speed_kmh`` x dt.

    Telemetry from :func:`t1f1.ingestion.decode.build_telemetry` already has this;
    useful again after :func:`slice_by_time`/:func:`resample_channels` change the
    sample grid.
    """
    if df.is_empty() or "speed_kmh" not in df.columns:
        return df
    df = df.sort("timestamp")
    dt_seconds = pl.col("timestamp").diff().dt.total_nanoseconds().cast(pl.Float64) / 1e9
    speed_ms = pl.col("speed_kmh").cast(pl.Float64) * _KMH_TO_MS
    distance = (speed_ms * dt_seconds.fill_null(0.0)).cum_sum().cast(pl.Float32).alias("distance")
    return df.with_columns(distance)


def add_differential_distance(df: pl.DataFrame) -> pl.DataFrame:
    """Add ``differential_distance``: the per-sample distance delta (m)."""
    if df.is_empty() or "distance" not in df.columns:
        return df
    return df.with_columns(
        pl.col("distance").diff().fill_null(0.0).cast(pl.Float32).alias("differential_distance")
    )


def add_relative_distance(df: pl.DataFrame) -> pl.DataFrame:
    """Add ``relative_distance``: ``distance`` normalised to ``0..1`` over the frame."""
    if df.is_empty() or "distance" not in df.columns:
        return df
    total = df["distance"].max()
    if not total:
        return df.with_columns(pl.lit(0.0, dtype=pl.Float32).alias("relative_distance"))
    return df.with_columns((pl.col("distance") / total).cast(pl.Float32).alias("relative_distance"))


def add_track_status(df: pl.DataFrame, track_status: pl.DataFrame) -> pl.DataFrame:
    """Stamp each sample's ``track_status`` via a nearest-before join on timestamp."""
    if df.is_empty() or track_status.is_empty():
        return df
    right = (
        track_status.select(["timestamp", "status"])
        .drop_nulls("timestamp")
        .sort("timestamp")
        .rename({"status": "track_status"})
    )
    if right.is_empty():
        return df
    left = df.sort("timestamp")
    return left.join_asof(right, on="timestamp", strategy="backward")


def merge_channels(df: pl.DataFrame, other: pl.DataFrame, *, on: str = "timestamp") -> pl.DataFrame:
    """Merge another frame's channels onto ``df`` by nearest ``on``-column match.

    E.g. merge weather samples onto car telemetry: ``merge_channels(tel, weather)``.
    Columns present in both frames are suffixed ``_right`` on the incoming side.
    """
    if df.is_empty() or other.is_empty():
        return df
    left = df.sort(on)
    right = other.drop_nulls(on).sort(on)
    if right.is_empty():
        return df
    overlapping = (set(right.columns) & set(left.columns)) - {on}
    if overlapping:
        right = right.rename({c: f"{c}_right" for c in overlapping})
    return left.join_asof(right, on=on, strategy="nearest")


def slice_by_time(df: pl.DataFrame, start, end) -> pl.DataFrame:
    """Keep samples with ``start <= timestamp <= end``."""
    if df.is_empty():
        return df
    return df.filter(pl.col("timestamp").is_between(start, end))


def slice_by_mask(df: pl.DataFrame, mask: pl.Series) -> pl.DataFrame:
    """Keep samples where the boolean ``mask`` is true."""
    if df.is_empty():
        return df
    return df.filter(mask)


def resample_channels(df: pl.DataFrame, every: str = "100ms") -> pl.DataFrame:
    """Resample onto a fixed-frequency time grid.

    Float channels (speed, throttle, distance, ...) are averaged per bucket;
    everything else (gear, DRS, driver, track_status, ...) takes the bucket's most
    recent sample — averaging a discrete channel like gear would be meaningless.
    """
    if df.is_empty():
        return df
    float_cols = [
        c for c, dt in df.schema.items() if dt in (pl.Float32, pl.Float64) and c != "timestamp"
    ]
    other_cols = [c for c in df.columns if c not in float_cols and c != "timestamp"]
    resampled = (
        df.sort("timestamp")
        .group_by_dynamic("timestamp", every=every)
        .agg(
            [pl.col(c).mean().alias(c) for c in float_cols]
            + [pl.col(c).last().alias(c) for c in other_cols]
        )
    )
    return resampled.select(df.columns).cast({c: df.schema[c] for c in float_cols})


def fill_missing(df: pl.DataFrame) -> pl.DataFrame:
    """Forward-fill (then back-fill any leading gap) every non-identity column."""
    if df.is_empty():
        return df
    key_cols = {"timestamp", "driver", "driver_number"}
    cols = [c for c in df.columns if c not in key_cols]
    return df.with_columns(
        [pl.col(c).fill_null(strategy="forward").fill_null(strategy="backward") for c in cols]
    )


def compute_driver_ahead(target: pl.DataFrame, others: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Add ``driver_ahead``/``distance_to_driver_ahead`` to ``target``'s telemetry.

    For each sample, every other driver's cumulative session ``distance`` is aligned
    to that timestamp (nearest match), and the nearest driver *ahead* (smallest
    positive distance gap) is recorded. ``others`` maps driver TLA -> that driver's
    telemetry (must include a ``distance`` column, e.g. from :func:`add_distance`).

    This compares cumulative session distance, so it's most meaningful within a
    shared lap/timeframe (typical on-track battles) rather than across drivers many
    laps apart.
    """
    empty_result = target.with_columns(
        pl.lit(None, dtype=pl.Utf8).alias("driver_ahead"),
        pl.lit(None, dtype=pl.Float32).alias("distance_to_driver_ahead"),
    )
    if target.is_empty() or "distance" not in target.columns or not others:
        return empty_result

    base = target.sort("timestamp")
    own_distance = base["distance"].to_numpy()

    tlas: list[str] = []
    gap_columns: list[np.ndarray] = []
    for tla, tel in others.items():
        if tel.is_empty() or "distance" not in tel.columns:
            continue
        aligned = base.select(["timestamp"]).join_asof(
            tel.select(["timestamp", "distance"]).sort("timestamp"),
            on="timestamp",
            strategy="nearest",
        )
        other_distance = aligned["distance"].to_numpy()
        gap = other_distance - own_distance
        gap_columns.append(np.where(gap > 0, gap, np.nan))
        tlas.append(tla)

    if not tlas:
        return empty_result

    gaps = np.column_stack(gap_columns)
    all_nan_rows = np.all(np.isnan(gaps), axis=1)
    gaps_filled = np.where(np.isnan(gaps), np.inf, gaps)
    best_idx = np.argmin(gaps_filled, axis=1)
    best_gap = np.where(all_nan_rows, np.nan, gaps_filled[np.arange(len(best_idx)), best_idx])
    driver_names = np.array(tlas, dtype=object)
    best_driver = np.where(all_nan_rows, None, driver_names[best_idx])

    return base.with_columns(
        pl.Series("driver_ahead", best_driver.tolist(), dtype=pl.Utf8),
        pl.Series("distance_to_driver_ahead", best_gap.tolist(), dtype=pl.Float32),
    )
