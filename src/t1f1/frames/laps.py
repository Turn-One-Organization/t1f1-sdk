"""``LapsFrame``: chainable, fastf1-parity filters over a laps frame."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import polars as pl


class LapsFrame:
    """Wraps a :data:`t1f1.schemas.LAP_SCHEMA`-typed ``pl.DataFrame`` with chainable
    ``pick_*`` filters. Every filter returns a new :class:`LapsFrame`; ``.frame``
    exposes the underlying polars frame for anything not covered here."""

    def __init__(self, frame: pl.DataFrame) -> None:
        self.frame = frame

    def __len__(self) -> int:
        return self.frame.height

    def __repr__(self) -> str:
        return f"LapsFrame({self.frame!r})"

    def _wrap(self, frame: pl.DataFrame) -> LapsFrame:
        return LapsFrame(frame)

    def to_polars(self) -> pl.DataFrame:
        return self.frame

    # -- selection --------------------------------------------------------

    def pick_drivers(self, *drivers: str) -> LapsFrame:
        wanted = {d.upper() for d in drivers}
        return self._wrap(self.frame.filter(pl.col("driver").is_in(wanted)))

    def pick_teams(self, *teams: str) -> LapsFrame:
        wanted = {t.lower() for t in teams}
        return self._wrap(self.frame.filter(pl.col("team").str.to_lowercase().is_in(wanted)))

    def pick_compounds(self, *compounds: str) -> LapsFrame:
        wanted = {c.upper() for c in compounds}
        return self._wrap(self.frame.filter(pl.col("compound").is_in(wanted)))

    def pick_laps(self, lap_numbers: int | list[int]) -> LapsFrame:
        numbers = [lap_numbers] if isinstance(lap_numbers, int) else list(lap_numbers)
        return self._wrap(self.frame.filter(pl.col("lap_number").is_in(numbers)))

    def pick_track_status(self, status: str) -> LapsFrame:
        return self._wrap(self.frame.filter(pl.col("track_status") == status))

    # -- quality filters ----------------------------------------------------

    def pick_not_deleted(self) -> LapsFrame:
        return self._wrap(self.frame.filter(~pl.col("deleted").fill_null(False)))

    def pick_accurate(self) -> LapsFrame:
        return self._wrap(self.frame.filter(pl.col("is_accurate").fill_null(True)))

    def pick_wo_box(self) -> LapsFrame:
        return self._wrap(
            self.frame.filter(pl.col("pit_in_time").is_null() & pl.col("pit_out_time").is_null())
        )

    def pick_box_laps(self) -> LapsFrame:
        return self._wrap(
            self.frame.filter(
                pl.col("pit_in_time").is_not_null() | pl.col("pit_out_time").is_not_null()
            )
        )

    def pick_quicklaps(self, threshold: float = 1.07) -> LapsFrame:
        """Keep laps within ``threshold`` x the fastest lap in the frame (107%-rule)."""
        if self.frame.is_empty():
            return self._wrap(self.frame)
        fastest = self.frame["lap_time"].min()
        if fastest is None:
            return self._wrap(self.frame.clear())
        return self._wrap(self.frame.filter(pl.col("lap_time") <= fastest * threshold))

    def pick_fastest(self) -> LapsFrame:
        """Return the single fastest lap in the frame, wrapped."""
        if self.frame.is_empty():
            return self._wrap(self.frame)
        return self._wrap(self.frame.sort("lap_time").head(1))

    # -- grouping -------------------------------------------------------

    def split_qualifying_sessions(self) -> list[LapsFrame]:
        """Split into per-knockout-segment frames, if a ``qualifying_segment``
        column is present (see ``ingestion.results.segment_qualifying_laps``);
        otherwise returns ``[self]`` unchanged."""
        if "qualifying_segment" not in self.frame.columns:
            return [self]
        return [
            self._wrap(group)
            for _, group in self.frame.sort("qualifying_segment").group_by(
                "qualifying_segment", maintain_order=True
            )
        ]

    def iterlaps(self) -> Iterator[dict[str, Any]]:
        yield from self.frame.iter_rows(named=True)
