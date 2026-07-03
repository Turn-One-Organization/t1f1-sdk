"""plotting.py: color/style tokens (no matplotlib/plotly dependency)."""

from __future__ import annotations

import importlib.util
from datetime import timedelta
from pathlib import Path

import polars as pl
import pytest

from t1f1.analysis import COMPARE_SCHEMA, PACE_SCHEMA, STINT_SCHEMA
from t1f1.plotting import (
    FALLBACK_COLOR,
    driver_team_map,
    get_compound_color,
    get_driver_color,
    get_driver_style,
    get_team_color,
)

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def _load_example_module(name: str):
    spec = importlib.util.spec_from_file_location(name, EXAMPLES_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_get_team_color_fuzzy_matches():
    assert get_team_color("Red Bull Racing") == get_team_color("red bull racing")
    assert get_team_color("McLaren") != get_team_color("Ferrari")


def test_get_team_color_unknown_returns_fallback():
    assert get_team_color("Some New Team") == FALLBACK_COLOR


def test_get_compound_color_case_insensitive():
    assert get_compound_color("soft") == get_compound_color("SOFT")
    assert get_compound_color("unknown") == FALLBACK_COLOR


def test_get_driver_color_via_teams_map():
    color = get_driver_color("VER", teams={"VER": "Red Bull Racing"})
    assert color == get_team_color("Red Bull Racing")


def test_get_driver_color_without_team_returns_fallback():
    assert get_driver_color("VER") == FALLBACK_COLOR


def test_get_driver_style_cycles_linestyle_for_teammates():
    s0 = get_driver_style("VER", team="Red Bull Racing", teammate_index=0)
    s1 = get_driver_style("PER", team="Red Bull Racing", teammate_index=1)
    assert s0["color"] == s1["color"]
    assert s0["linestyle"] != s1["linestyle"]


def test_driver_team_map_builds_lookup():
    frame = pl.DataFrame(
        {
            "driver": ["VER", "NOR", "VER"],
            "team": ["Red Bull Racing", "McLaren", "Red Bull Racing"],
        }
    )
    assert driver_team_map(frame) == {"VER": "Red Bull Racing", "NOR": "McLaren"}


def test_driver_team_map_empty_frame():
    assert driver_team_map(pl.DataFrame()) == {}


def test_plotting_matplotlib_example_produces_charts(tmp_path):
    """Smoke test: examples/plotting_matplotlib.py's chart builders run end to end
    against tiny synthetic analysis outputs, using the headless ``Agg`` backend."""
    pytest.importorskip("matplotlib")
    module = _load_example_module("plotting_matplotlib")

    teams = {"VER": "Red Bull Racing", "NOR": "McLaren"}

    pace = pl.DataFrame(
        [
            {
                "driver": "VER",
                "laps": 20,
                "min": timedelta(seconds=80.0),
                "q1": timedelta(seconds=80.2),
                "median": timedelta(seconds=80.4),
                "q3": timedelta(seconds=80.6),
                "max": timedelta(seconds=81.0),
            },
            {
                "driver": "NOR",
                "laps": 20,
                "min": timedelta(seconds=80.3),
                "q1": timedelta(seconds=80.5),
                "median": timedelta(seconds=80.7),
                "q3": timedelta(seconds=80.9),
                "max": timedelta(seconds=81.3),
            },
        ],
        schema=PACE_SCHEMA,
    )
    module.plot_lap_times(pace, teams, tmp_path / "lap_times.png")

    stints = pl.DataFrame(
        [
            {
                "driver": "VER",
                "team": "Red Bull Racing",
                "stint": 1,
                "compound": "MEDIUM",
                "start_lap": 1,
                "end_lap": 10,
                "lap_count": 10,
            },
            {
                "driver": "VER",
                "team": "Red Bull Racing",
                "stint": 2,
                "compound": "HARD",
                "start_lap": 11,
                "end_lap": 20,
                "lap_count": 10,
            },
            {
                "driver": "NOR",
                "team": "McLaren",
                "stint": 1,
                "compound": "SOFT",
                "start_lap": 1,
                "end_lap": 15,
                "lap_count": 15,
            },
        ],
        schema=STINT_SCHEMA,
    )
    module.plot_tyre_stints(stints, tmp_path / "tyre_stints.png")

    comparison = pl.DataFrame(
        [
            {
                "distance": float(i * 25),
                "delta_seconds": 0.01 * i,
                "driver1_speed_kmh": 300.0 + i,
                "driver2_speed_kmh": 295.0 + i,
                "driver1_throttle": 100.0,
                "driver2_throttle": 100.0,
                "driver1_brake": 0.0,
                "driver2_brake": 0.0,
            }
            for i in range(10)
        ],
        schema=COMPARE_SCHEMA,
    )
    module.plot_telemetry_compare(
        comparison, "VER", "NOR", 12, teams, tmp_path / "telemetry_compare.png"
    )

    assert (tmp_path / "lap_times.png").exists()
    assert (tmp_path / "tyre_stints.png").exists()
    assert (tmp_path / "telemetry_compare.png").exists()
