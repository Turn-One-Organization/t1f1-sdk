"""Session objects: the primary user-facing handle for one F1 session.

``AsyncSession`` is the async core; ``Session`` is a blocking facade over it. Raw
per-sample telemetry always comes from the free F1 engine; analysis methods prefer the
premium T1API source when an API key was supplied.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from t1f1.sources.raw_f1 import RawF1Source
from t1f1.sources.t1api import T1APISource

if TYPE_CHECKING:
    from t1f1._sync import LoopThread


class AsyncSession:
    """Async handle for a single ``(year, gp, session)``."""

    def __init__(
        self,
        year: int,
        gp: int | str,
        session: str,
        *,
        raw: RawF1Source,
        premium: T1APISource | None = None,
    ) -> None:
        self.year = year
        self.gp = gp
        self.session = session
        self._raw = raw
        self._premium = premium

    @property
    def is_premium(self) -> bool:
        return self._premium is not None

    def _analysis_source(self) -> RawF1Source | T1APISource:
        """Prefer the premium source for analysis; fall back to the raw engine."""
        return self._premium or self._raw

    # -- raw telemetry: always the free F1 engine -----------------------------

    async def telemetry(self, driver: str) -> pl.DataFrame:
        return await self._raw.telemetry(driver)

    # -- analysis: premium if keyed, else computed locally --------------------

    async def top_speeds(self) -> pl.DataFrame:
        return await self._analysis_source().top_speeds()


class Session:
    """Blocking facade over :class:`AsyncSession`."""

    def __init__(self, loop: LoopThread, inner: AsyncSession) -> None:
        self._loop = loop
        self._inner = inner

    @property
    def year(self) -> int:
        return self._inner.year

    @property
    def gp(self) -> int | str:
        return self._inner.gp

    @property
    def session(self) -> str:
        return self._inner.session

    @property
    def is_premium(self) -> bool:
        return self._inner.is_premium

    def telemetry(self, driver: str) -> pl.DataFrame:
        return self._loop.run(self._inner.telemetry(driver))

    def top_speeds(self) -> pl.DataFrame:
        return self._loop.run(self._inner.top_speeds())
