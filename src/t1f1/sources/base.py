"""The ``DataSource`` protocol both tiers implement.

This is the seam the backend's ``ingestion/base.py`` flagged as future work
("define typed DTOs for telemetry / lap_times / results that both sources produce").
Raw per-sample ``telemetry`` always comes from the F1 feed; analysis methods are the
ones that reroute to T1API when an API key is present.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import polars as pl


@runtime_checkable
class DataSource(Protocol):
    """A source that can produce telemetry and analysis products for one session."""

    async def telemetry(self, driver: str) -> pl.DataFrame:
        """Per-sample telemetry for ``driver`` as a canonical polars frame."""
        ...

    async def top_speeds(self) -> pl.DataFrame:
        """Per-driver peak speed for the session."""
        ...
