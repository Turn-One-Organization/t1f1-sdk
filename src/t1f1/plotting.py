"""Team/driver/compound color & style tokens — usable from matplotlib *and* plotly.

Deliberately not coupled to matplotlib (unlike fastf1's ``plotting`` module, which
returns colormap objects and mutates rcParams): every function here returns plain
strings/dicts, so the same token works whether you're building a matplotlib
``Line2D`` or a plotly ``go.Scatter``. Actual chart-rendering helpers (fastf1's
``.plot()``-style wrappers) are intentionally not included here — that's future
work behind an optional ``t1f1-sdk[plot]`` extra so the core package stays
dependency-free.
"""

from __future__ import annotations

import re

import polars as pl

#: 2024-season team colors (hex). Team names/liveries change season to season —
#: pass a fresher mapping via ``palette=`` on any lookup below if these go stale.
TEAM_COLORS: dict[str, str] = {
    "red bull racing": "#3671C6",
    "ferrari": "#E8002D",
    "mercedes": "#27F4D2",
    "mclaren": "#FF8000",
    "aston martin": "#229971",
    "alpine": "#FF87BC",
    "williams": "#64C4FF",
    "rb": "#6692FF",
    "kick sauber": "#52E252",
    "haas f1 team": "#B6BABD",
}

#: Tyre compound colors — the standard Pirelli/FIA convention (stable across seasons).
COMPOUND_COLORS: dict[str, str] = {
    "SOFT": "#FF3333",
    "MEDIUM": "#FFF200",
    "HARD": "#EBEBEB",
    "INTERMEDIATE": "#43B02A",
    "WET": "#0067AD",
}

#: Returned for a team/compound that doesn't match anything in the palette, rather
#: than raising — new team names/entrants appear most seasons.
FALLBACK_COLOR = "#808080"

#: Cycled by :func:`get_driver_style` so teammates (same team color) stay visually
#: distinguishable on an overlaid line plot.
LINESTYLES: tuple[str, ...] = ("solid", "dashed", "dotted", "dashdot")


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def get_team_color(team: str, *, palette: dict[str, str] | None = None) -> str:
    """Hex color for a team name (fuzzy-matched: exact, then substring)."""
    colors = palette or TEAM_COLORS
    target = _normalize(team)
    for name, color in colors.items():
        normalized = _normalize(name)
        if target == normalized or target in normalized or normalized in target:
            return color
    return FALLBACK_COLOR


def get_compound_color(compound: str, *, palette: dict[str, str] | None = None) -> str:
    """Hex color for a tyre compound name (case-insensitive)."""
    colors = palette or COMPOUND_COLORS
    return colors.get(str(compound).upper(), FALLBACK_COLOR)


def get_driver_color(
    driver: str,
    *,
    team: str | None = None,
    teams: dict[str, str] | None = None,
    palette: dict[str, str] | None = None,
) -> str:
    """Hex color for a driver, resolved via their team.

    Pass ``team`` directly, or ``teams`` (a ``{driver: team}`` map — e.g. from
    :func:`driver_team_map`) — deliberately dynamic rather than a hardcoded driver
    roster, which would go stale on every driver transfer.
    """
    resolved_team = team
    if resolved_team is None and teams:
        resolved_team = teams.get(driver.upper()) or teams.get(driver)
    if resolved_team is None:
        return FALLBACK_COLOR
    return get_team_color(resolved_team, palette=palette)


def get_driver_style(
    driver: str,
    *,
    team: str | None = None,
    teams: dict[str, str] | None = None,
    teammate_index: int = 0,
    palette: dict[str, str] | None = None,
) -> dict[str, str]:
    """Color + linestyle for a driver. Teammates share a team color but get a
    different ``linestyle`` (cycle through ``teammate_index`` 0/1/2/...) so an
    overlaid line plot of same-team drivers stays distinguishable."""
    return {
        "color": get_driver_color(driver, team=team, teams=teams, palette=palette),
        "linestyle": LINESTYLES[teammate_index % len(LINESTYLES)],
    }


def driver_team_map(frame: pl.DataFrame) -> dict[str, str]:
    """Build a ``{driver: team}`` lookup from a ``results()``/``laps()`` frame — the
    normal way to populate ``teams=`` above without a hardcoded roster."""
    if frame.is_empty() or "driver" not in frame.columns or "team" not in frame.columns:
        return {}
    pairs = frame.select(["driver", "team"]).unique()
    return {row["driver"]: row["team"] for row in pairs.iter_rows(named=True) if row["driver"]}
