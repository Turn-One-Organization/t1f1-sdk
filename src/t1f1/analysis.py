"""Free-tier analysis products: vectorized local compute over laps()/telemetry().

Each function here is pure — it takes already-fetched frames and returns a new one,
so it's fully testable offline. The premium (T1API) counterparts, when a key is
present, are wired in ``sources/t1api.py``; ``AsyncSession`` prefers premium and
falls back to these functions (see ``session.py``).
"""

from __future__ import annotations

import numpy as np
import polars as pl

from t1f1.frames.laps import LapsFrame
from t1f1.utils import delta_time

PACE_SCHEMA: dict[str, pl.DataType] = {
    "driver": pl.Utf8,
    "laps": pl.Int32,
    "min": pl.Duration("ms"),
    "q1": pl.Duration("ms"),
    "median": pl.Duration("ms"),
    "q3": pl.Duration("ms"),
    "max": pl.Duration("ms"),
}

TEAM_PACE_SCHEMA: dict[str, pl.DataType] = {
    "team": pl.Utf8,
    **{k: v for k, v in PACE_SCHEMA.items() if k != "driver"},
}

STINT_SCHEMA: dict[str, pl.DataType] = {
    "driver": pl.Utf8,
    "team": pl.Utf8,
    "stint": pl.Int32,
    "compound": pl.Utf8,
    "start_lap": pl.Int32,
    "end_lap": pl.Int32,
    "lap_count": pl.Int32,
}

SPEED_TRAP_SCHEMA: dict[str, pl.DataType] = {
    "driver": pl.Utf8,
    "lap_number": pl.Int32,
    "top_speed_kmh": pl.Float32,
}

SPEED_DISTRIBUTION_SCHEMA: dict[str, pl.DataType] = {
    "bin_start": pl.Float32,
    "bin_end": pl.Float32,
    "count": pl.Int32,
}

COMPARE_SCHEMA: dict[str, pl.DataType] = {
    "distance": pl.Float32,
    "delta_seconds": pl.Float32,
    "driver1_speed_kmh": pl.Float32,
    "driver2_speed_kmh": pl.Float32,
    "driver1_throttle": pl.Float32,
    "driver2_throttle": pl.Float32,
    "driver1_brake": pl.Float32,
    "driver2_brake": pl.Float32,
}

TRACK_DOMINANCE_SCHEMA: dict[str, pl.DataType] = {
    "minisector": pl.Int32,
    "driver1_avg_speed_kmh": pl.Float32,
    "driver2_avg_speed_kmh": pl.Float32,
    "faster": pl.Utf8,
}


def speed_trap_top_speeds(laps: pl.DataFrame) -> pl.DataFrame:
    """Peak official speed-trap reading (``speed_st``) per driver, from ``laps()``.

    Distinct from ``RawF1Source.top_speeds()``, which takes the max instantaneous
    CarData speed across the whole session — this uses the fixed speed-trap
    measurement point instead (T1API's "top-speed-st" split).
    """
    valid = laps.filter(pl.col("speed_st").is_not_null()) if not laps.is_empty() else laps
    if valid.is_empty():
        return pl.DataFrame(schema=SPEED_TRAP_SCHEMA)
    top = (
        valid.sort("speed_st", descending=True)
        .unique(subset="driver", keep="first")
        .select(
            pl.col("driver"),
            pl.col("lap_number"),
            pl.col("speed_st").alias("top_speed_kmh"),
        )
        .sort("top_speed_kmh", descending=True)
    )
    return top.cast(SPEED_TRAP_SCHEMA)


def _pace_stats(
    quick: pl.DataFrame, group_col: str, schema: dict[str, pl.DataType]
) -> pl.DataFrame:
    if quick.is_empty():
        return pl.DataFrame(schema=schema)
    stats = (
        quick.group_by(group_col)
        .agg(
            pl.len().cast(pl.Int32).alias("laps"),
            pl.col("lap_time").min().alias("min"),
            pl.col("lap_time").quantile(0.25).alias("q1"),
            pl.col("lap_time").median().alias("median"),
            pl.col("lap_time").quantile(0.75).alias("q3"),
            pl.col("lap_time").max().alias("max"),
        )
        .sort("median")
    )
    return stats.cast(schema)


def driver_pace(laps: pl.DataFrame, *, threshold: float = 1.07) -> pl.DataFrame:
    """Box-and-whisker pace per driver: quicklaps (``threshold`` x session-best,
    the 107% rule by default), excluding deleted laps and in/out laps."""
    quick = LapsFrame(laps).pick_not_deleted().pick_wo_box().pick_quicklaps(threshold).to_polars()
    return _pace_stats(quick, "driver", PACE_SCHEMA)


def teams_pace(laps: pl.DataFrame, *, threshold: float = 1.07) -> pl.DataFrame:
    """Box-and-whisker pace per team (see :func:`driver_pace`)."""
    quick = LapsFrame(laps).pick_not_deleted().pick_wo_box().pick_quicklaps(threshold).to_polars()
    return _pace_stats(quick, "team", TEAM_PACE_SCHEMA)


def tyre_stints(laps: pl.DataFrame) -> pl.DataFrame:
    """Per-driver stint timeline: compound, start/end lap, lap count."""
    if laps.is_empty():
        return pl.DataFrame(schema=STINT_SCHEMA)
    stints = (
        laps.group_by(["driver", "team", "stint"])
        .agg(
            pl.col("compound").first(),
            pl.col("lap_number").min().alias("start_lap"),
            pl.col("lap_number").max().alias("end_lap"),
            pl.len().cast(pl.Int32).alias("lap_count"),
        )
        .sort(["driver", "stint"])
    )
    return stints.cast(STINT_SCHEMA)


def qualifying_results(results: pl.DataFrame) -> pl.DataFrame:
    """``results()`` sorted by gap-to-pole, using the best of Q3/Q2/Q1 (whichever a
    driver's classification actually reached) as their qualifying time."""
    if results.is_empty():
        return results.with_columns(pl.lit(None, dtype=pl.Duration("ms")).alias("gap_to_pole"))
    with_best = results.with_columns(pl.coalesce(["q3", "q2", "q1"]).alias("_qualifying_best"))
    pole = with_best["_qualifying_best"].min()
    return (
        with_best.with_columns((pl.col("_qualifying_best") - pole).alias("gap_to_pole"))
        .drop("_qualifying_best")
        .sort("position")
    )


def speed_distribution(telemetry: pl.DataFrame, *, bins: int = 20) -> pl.DataFrame:
    """Histogram of ``speed_kmh`` samples."""
    if telemetry.is_empty():
        return pl.DataFrame(schema=SPEED_DISTRIBUTION_SCHEMA)
    speeds = telemetry["speed_kmh"].drop_nulls().to_numpy()
    if speeds.size == 0:
        return pl.DataFrame(schema=SPEED_DISTRIBUTION_SCHEMA)
    counts, edges = np.histogram(speeds, bins=bins)
    return pl.DataFrame(
        {
            "bin_start": edges[:-1].astype("float32"),
            "bin_end": edges[1:].astype("float32"),
            "count": counts.astype("int32"),
        }
    )


def compare(tel1: pl.DataFrame, tel2: pl.DataFrame) -> pl.DataFrame:
    """Distance-aligned comparison of two laps' telemetry + time delta.

    ``tel1``/``tel2`` should each be one lap's telemetry (e.g. from
    ``RawF1Source.lap_telemetry``) with a ``distance`` column. Returns one row per
    ``tel1`` sample: ``distance``, ``delta_seconds`` (positive = driver2 behind at
    that point, from :func:`t1f1.utils.delta_time`), and both drivers'
    speed/throttle/brake aligned to that same distance.
    """
    if tel1.is_empty() or tel2.is_empty():
        return pl.DataFrame(schema=COMPARE_SCHEMA)

    delta = delta_time(tel1, tel2)
    ref = (
        tel1.sort("distance")
        .select(["distance", "speed_kmh", "throttle", "brake"])
        .rename(
            {
                "speed_kmh": "driver1_speed_kmh",
                "throttle": "driver1_throttle",
                "brake": "driver1_brake",
            }
        )
    )
    comp = (
        tel2.sort("distance")
        .select(["distance", "speed_kmh", "throttle", "brake"])
        .rename(
            {
                "speed_kmh": "driver2_speed_kmh",
                "throttle": "driver2_throttle",
                "brake": "driver2_brake",
            }
        )
    )
    merged = ref.join_asof(comp, on="distance", strategy="nearest")
    merged = merged.join_asof(
        delta.select(["distance", "delta_seconds"]), on="distance", strategy="nearest"
    )
    return merged.select(list(COMPARE_SCHEMA)).cast(COMPARE_SCHEMA)


def track_dominance(
    tel1: pl.DataFrame,
    tel2: pl.DataFrame,
    *,
    driver1: str,
    driver2: str,
    n_minisectors: int = 25,
) -> pl.DataFrame:
    """Average speed per minisector (equal ``relative_distance`` bins) for two laps,
    tagging which driver was faster in each. A common fastf1-community
    visualization that fastf1 itself doesn't ship as a built-in method.

    ``tel1``/``tel2`` must already carry ``relative_distance`` (see
    ``frames.telemetry.add_relative_distance``).
    """
    if (
        tel1.is_empty()
        or tel2.is_empty()
        or "relative_distance" not in tel1.columns
        or "relative_distance" not in tel2.columns
    ):
        return pl.DataFrame(schema=TRACK_DOMINANCE_SCHEMA)

    def _binned(tel: pl.DataFrame, column: str) -> pl.DataFrame:
        return (
            tel.with_columns(
                (pl.col("relative_distance") * n_minisectors)
                .floor()
                .clip(0, n_minisectors - 1)
                .cast(pl.Int32)
                .alias("minisector")
            )
            .group_by("minisector")
            .agg(pl.col("speed_kmh").mean().alias(column))
        )

    b1 = _binned(tel1, "driver1_avg_speed_kmh")
    b2 = _binned(tel2, "driver2_avg_speed_kmh")
    merged = b1.join(b2, on="minisector", how="full", coalesce=True).sort("minisector")
    result = merged.with_columns(
        pl.when(pl.col("driver1_avg_speed_kmh") > pl.col("driver2_avg_speed_kmh"))
        .then(pl.lit(driver1))
        .when(pl.col("driver2_avg_speed_kmh") > pl.col("driver1_avg_speed_kmh"))
        .then(pl.lit(driver2))
        .otherwise(None)
        .alias("faster")
    )
    return result.select(list(TRACK_DOMINANCE_SCHEMA)).cast(TRACK_DOMINANCE_SCHEMA)
