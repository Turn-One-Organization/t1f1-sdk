"""Matplotlib recipes on top of t1f1's analysis + plotting-token APIs.

Fetches a real session from the free F1 live-timing feed (no API key needed) and
renders it with a dark, broadcast-style theme. Requires the ``plot`` extra:
``pip install -e ".[plot]"``.

Produces three PNGs in ``examples/output/``:
  - lap_times.png         (driver_pace box-and-whisker)
  - tyre_stints.png       (stint timeline)
  - telemetry_compare.png (speed trace + time-delta overlay)
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless-safe; drop this line to use an interactive backend
import matplotlib.pyplot as plt
import polars as pl

from t1f1 import Client
from t1f1.plotting import driver_team_map, get_compound_color, get_driver_style, get_team_color

OUTPUT_DIR = Path(__file__).parent / "output"

YEAR = 2026
GRAND_PRIX = "Austrian Grand Prix"
SESSION = "R"

# -- dark, broadcast-style theme ----------------------------------------------

BG = "#15151E"
FG = "#F5F5F5"
GRID = "#38383F"

plt.rcParams.update(
    {
        "figure.facecolor": BG,
        "axes.facecolor": BG,
        "axes.edgecolor": GRID,
        "axes.labelcolor": FG,
        "text.color": FG,
        "xtick.color": FG,
        "ytick.color": FG,
        "grid.color": GRID,
        "font.size": 11,
    }
)


def _style_axes(ax: plt.Axes) -> None:
    ax.grid(True, alpha=0.4, linewidth=0.6)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_color(GRID)


def plot_lap_times(pace: pl.DataFrame, teams: dict[str, str], out: Path) -> None:
    """Box-and-whisker race pace per driver (from :func:`t1f1.analysis.driver_pace`),
    colored by team, built directly from the summary stats via ``ax.bxp``."""
    stats = [
        {
            "label": row["driver"],
            "med": row["median"].total_seconds(),
            "q1": row["q1"].total_seconds(),
            "q3": row["q3"].total_seconds(),
            "whislo": row["min"].total_seconds(),
            "whishi": row["max"].total_seconds(),
            "fliers": [],
        }
        for row in pace.iter_rows(named=True)
    ]

    fig, ax = plt.subplots(figsize=(max(8, len(stats) * 0.55), 5))
    boxes = ax.bxp(stats, patch_artist=True, showfliers=False)
    for patch, row in zip(boxes["boxes"], pace.iter_rows(named=True), strict=True):
        color = get_team_color(teams.get(row["driver"], ""))
        patch.set_facecolor(color)
        patch.set_edgecolor(FG)
        patch.set_alpha(0.9)
    for element in ("whiskers", "caps", "medians"):
        for artist in boxes[element]:
            artist.set_color(FG)

    _style_axes(ax)
    ax.set_ylabel("Lap time (s)")
    ax.set_title(f"{GRAND_PRIX} {YEAR} — race pace by driver (quicklaps)")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_tyre_stints(stints: pl.DataFrame, out: Path) -> None:
    """Horizontal stint timeline per driver, colored by compound."""
    drivers = (
        stints.group_by("driver")
        .agg(pl.col("end_lap").max())
        .sort("end_lap", descending=True)["driver"]
        .to_list()
    )

    fig, ax = plt.subplots(figsize=(9, max(5, len(drivers) * 0.35)))
    for row in stints.iter_rows(named=True):
        y = drivers.index(row["driver"])
        ax.barh(
            y,
            row["lap_count"],
            left=row["start_lap"] - 1,
            color=get_compound_color(row["compound"]),
            edgecolor=BG,
            height=0.8,
        )
    ax.set_yticks(range(len(drivers)))
    ax.set_yticklabels(drivers, fontsize=8)
    ax.invert_yaxis()
    _style_axes(ax)
    ax.set_xlabel("Lap number")
    ax.set_title(f"{GRAND_PRIX} {YEAR} — tyre stints")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_telemetry_compare(
    comparison: pl.DataFrame,
    driver1: str,
    driver2: str,
    lap_number: int,
    teams: dict[str, str],
    out: Path,
) -> None:
    """Speed trace overlay + cumulative time-delta panel for two drivers' laps,
    teammate-aware styling via :func:`t1f1.plotting.get_driver_style`."""
    style1 = get_driver_style(driver1, teams=teams, teammate_index=0)
    style2 = get_driver_style(driver2, teams=teams, teammate_index=1)

    fig, (ax_speed, ax_delta) = plt.subplots(
        2, 1, figsize=(9, 6), sharex=True, height_ratios=[2, 1]
    )
    ax_speed.plot(comparison["distance"], comparison["driver1_speed_kmh"], label=driver1, **style1)
    ax_speed.plot(comparison["distance"], comparison["driver2_speed_kmh"], label=driver2, **style2)
    ax_speed.set_ylabel("Speed (km/h)")
    ax_speed.set_title(f"{driver1} vs {driver2} — lap {lap_number}, {GRAND_PRIX} {YEAR}")
    ax_speed.legend(facecolor=BG, edgecolor=GRID, labelcolor=FG)
    _style_axes(ax_speed)

    ax_delta.axhline(0, color=GRID, linewidth=1)
    ax_delta.fill_between(
        comparison["distance"], comparison["delta_seconds"], 0, color=style1["color"], alpha=0.5
    )
    ax_delta.set_xlabel("Distance (m)")
    ax_delta.set_ylabel(f"Gap to {driver2} (s)")
    _style_axes(ax_delta)

    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


#: The shortest F1 circuit (Monaco) is ~3.3 km; a lap with a real telemetry
#: sample covering less distance than this indicates a CarData dropout for that
#: window, not a genuinely short lap.
_MIN_LAP_DISTANCE_M = 3000.0


def _pick_comparable_lap(session, driver1: str, driver2: str, laps: pl.DataFrame) -> int:
    """Find a lap number with *usable* telemetry for both drivers.

    The free live-timing feed's CarData stream can drop out for a stretch of a
    real race (a known feed quirk, not something the SDK can paper over) — a
    driver's *fastest* lap is often outside that window, and a dropout lap's
    ``lap_telemetry`` frame is non-empty but flatlined (speed stuck at 0m
    covered). Scan lap numbers common to both drivers, fastest-first, and use
    the first one where both drivers' telemetry actually covers real distance.
    """
    common_laps = (
        laps.filter(pl.col("driver").is_in([driver1, driver2]))
        .group_by("lap_number")
        .agg(pl.col("driver").n_unique().alias("n"), pl.col("lap_time").min().alias("lap_time"))
        .filter(pl.col("n") == 2)
        .sort("lap_time")
    )
    for lap_number in common_laps["lap_number"].to_list():
        tel1 = session.lap_telemetry(driver1, lap_number)
        tel2 = session.lap_telemetry(driver2, lap_number)
        if (
            not tel1.is_empty()
            and not tel2.is_empty()
            and tel1["distance"].max() > _MIN_LAP_DISTANCE_M
            and tel2["distance"].max() > _MIN_LAP_DISTANCE_M
        ):
            return lap_number
    raise RuntimeError(f"no lap with usable telemetry for both {driver1} and {driver2}")


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    with Client() as client:
        session = client.session(YEAR, GRAND_PRIX, SESSION)
        results = session.results()
        teams = driver_team_map(results)

        pace = session.driver_pace()
        plot_lap_times(pace, teams, OUTPUT_DIR / "lap_times.png")

        stints = session.tyre_stints()
        plot_tyre_stints(stints, OUTPUT_DIR / "tyre_stints.png")

        driver1, driver2 = results.sort("position")["driver"][:2].to_list()
        laps = session.laps().to_polars()
        lap_number = _pick_comparable_lap(session, driver1, driver2, laps)
        comparison = session.compare(driver1, driver2, lap1=lap_number, lap2=lap_number)
        plot_telemetry_compare(
            comparison, driver1, driver2, lap_number, teams, OUTPUT_DIR / "telemetry_compare.png"
        )

    print(f"Wrote 3 PNGs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
