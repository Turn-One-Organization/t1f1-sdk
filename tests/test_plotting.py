"""plotting.py: color/style tokens (no matplotlib/plotly dependency)."""

from __future__ import annotations

import polars as pl

from t1f1.plotting import (
    FALLBACK_COLOR,
    driver_team_map,
    get_compound_color,
    get_driver_color,
    get_driver_style,
    get_team_color,
)


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
