# Plotting API

```python
from t1f1.plotting import (
    get_team_color, get_compound_color, get_driver_color, get_driver_style,
    driver_team_map, TEAM_COLORS, COMPOUND_COLORS, FALLBACK_COLOR, LINESTYLES,
)
```

Team/driver/compound color and style **tokens** — plain strings and dicts, not
chart objects. Deliberately not coupled to matplotlib (unlike fastf1's `plotting`
module, which returns colormap objects and mutates global `rcParams`): the same
token works whether you're building a matplotlib `Line2D` or a plotly
`go.Scatter`. No matplotlib import anywhere in this module, so it costs nothing if
you don't plot.

> Actual chart-rendering helpers (fastf1's `.plot()`-style wrappers) aren't
> included — that's future work behind an optional `t1f1-sdk[plot]` extra so the
> core package stays dependency-free.

## `get_team_color(team: str, *, palette: dict[str, str] | None = None) -> str`

Hex color for a team name, fuzzy-matched (exact match, then substring). Falls back
to `FALLBACK_COLOR` (`"#808080"`) for an unrecognized team rather than raising —
new entrants/renames happen most seasons.

```python
get_team_color("Red Bull Racing")   # "#3671C6"
get_team_color("red bull")          # "#3671C6" — case-insensitive, fuzzy
get_team_color("Some New Team")     # "#808080" — fallback, doesn't raise
```

## `get_compound_color(compound: str, *, palette: dict[str, str] | None = None) -> str`

Hex color for a tyre compound (case-insensitive), the standard Pirelli/FIA
convention.

```python
get_compound_color("SOFT")   # "#FF3333"
get_compound_color("hard")   # "#EBEBEB"
```

## `get_driver_color(driver, *, team=None, teams=None, palette=None) -> str`

Hex color for a driver, resolved via their team — pass `team` directly, or `teams`
(a `{driver: team}` map, typically from `driver_team_map()`). Deliberately dynamic
rather than a hardcoded driver roster, which would go stale on every driver
transfer.

```python
get_driver_color("VER", team="Red Bull Racing")

teams = driver_team_map(session.results())
get_driver_color("VER", teams=teams)
get_driver_color("NOR", teams=teams)
```

## `get_driver_style(driver, *, team=None, teams=None, teammate_index=0, palette=None) -> dict`

Color + linestyle for one driver. Teammates share a team color but get a different
`linestyle` (cycled via `teammate_index`) so an overlaid line plot of same-team
drivers stays visually distinguishable.

```python
style = get_driver_style("VER", teams=teams, teammate_index=0)
# {"color": "#3671C6", "linestyle": "solid"}

teammate_style = get_driver_style("PER", teams=teams, teammate_index=1)
# {"color": "#3671C6", "linestyle": "dashed"}
```

## `driver_team_map(frame: pl.DataFrame) -> dict[str, str]`

Build a `{driver: team}` lookup from a `results()`/`laps()` frame — the normal way
to populate `teams=` above.

```python
teams = driver_team_map(session.results())
# {"VER": "Red Bull Racing", "NOR": "McLaren", ...}
```

> See the [matplotlib tutorial](../tutorials/matplotlib-plots.md) for full,
> runnable recipes (race pace, tyre stints, speed-trace comparison) with rendered
> output.

## Putting it together — a matplotlib example

```python
import matplotlib.pyplot as plt
from t1f1.plotting import driver_team_map, get_driver_style

session = client.session(2024, "Monza", "Q")
teams = driver_team_map(session.results())

fig, ax = plt.subplots()
for i, driver in enumerate(["VER", "PER"]):  # teammates
    tel = session.telemetry(driver)
    style = get_driver_style(driver, teams=teams, teammate_index=i)
    ax.plot(tel["distance"], tel["speed_kmh"], label=driver, **style)
ax.legend()
```

## Tokens (for a custom palette)

- `TEAM_COLORS: dict[str, str]` — 2024-season team name -> hex. Pass a fresher
  mapping via `palette=` on any lookup above once liveries change.
- `COMPOUND_COLORS: dict[str, str]` — `SOFT`/`MEDIUM`/`HARD`/`INTERMEDIATE`/`WET`.
- `FALLBACK_COLOR: str` — `"#808080"`, returned for anything unmatched.
- `LINESTYLES: tuple[str, ...]` — `("solid", "dashed", "dotted", "dashdot")`, cycled
  by `get_driver_style`.
