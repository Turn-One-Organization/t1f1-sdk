"""Session objects: the primary user-facing handle for one F1 session.

``AsyncSession`` is the async core; ``Session`` is a blocking facade over it. Raw
per-sample telemetry always comes from the free F1 engine; analysis methods prefer the
premium T1API source when an API key was supplied, and transparently fall back to
local free-tier compute if the premium call fails with a retryable upstream error
(``PREMIUM_FALLBACK_ERRORS``) — a bad API key still raises, since that's a
configuration mistake the caller should see, not something to paper over.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import polars as pl

from t1f1.exceptions import PREMIUM_FALLBACK_ERRORS
from t1f1.frames.laps import LapsFrame
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
        #: Which tier served the most recently completed dual-tier analysis call:
        #: ``"t1api"`` or ``"free"``. ``None`` before any such call. A simple
        #: last-write, not per-call state — not meaningful under concurrent
        #: overlapping calls on the same session.
        self.last_source: str | None = None

    @property
    def is_premium(self) -> bool:
        return self._premium is not None

    async def _premium_then_free(
        self,
        premium: Callable[[], Awaitable[pl.DataFrame]] | None,
        free: Callable[[], Awaitable[pl.DataFrame]],
    ) -> pl.DataFrame:
        """Try ``premium`` (when available) and fall back to ``free`` if it raises a
        retryable upstream error; sets :attr:`last_source` to whichever actually
        served the result."""
        if premium is not None:
            try:
                result = await premium()
                self.last_source = "t1api"
                return result
            except PREMIUM_FALLBACK_ERRORS:
                pass  # premium had a bad moment — degrade to local compute below
        result = await free()
        self.last_source = "free"
        return result

    # -- raw telemetry: always the free F1 engine -----------------------------

    async def telemetry(self, driver: str) -> pl.DataFrame:
        return await self._raw.telemetry(driver)

    async def lap_telemetry(self, driver: str, lap_number: int) -> pl.DataFrame:
        return await self._raw.lap_telemetry(driver, lap_number)

    async def driver_ahead(self, driver: str) -> pl.DataFrame:
        return await self._raw.driver_ahead(driver)

    # -- analysis: premium if keyed, else computed locally --------------------

    async def top_speeds(self) -> pl.DataFrame:
        premium = self._premium.top_speeds if self._premium is not None else None
        return await self._premium_then_free(premium, self._raw.top_speeds)

    async def speed_trap_top_speeds(self) -> pl.DataFrame:
        premium = self._premium.speed_trap_top_speeds if self._premium is not None else None
        return await self._premium_then_free(premium, self._raw.speed_trap_top_speeds)

    async def tyre_stints(self) -> pl.DataFrame:
        premium = self._premium.tyre_stints if self._premium is not None else None
        return await self._premium_then_free(premium, self._raw.tyre_stints)

    async def qualifying_results(self) -> pl.DataFrame:
        premium = self._premium.qualifying_results if self._premium is not None else None
        return await self._premium_then_free(premium, self._raw.qualifying_results)

    async def driver_pace(self, *, threshold: float = 1.07) -> pl.DataFrame:
        premium = self._premium.driver_pace if self._premium is not None else None
        free = functools.partial(self._raw.driver_pace, threshold=threshold)
        return await self._premium_then_free(premium, free)

    async def teams_pace(self, *, threshold: float = 1.07) -> pl.DataFrame:
        premium = self._premium.teams_pace if self._premium is not None else None
        free = functools.partial(self._raw.teams_pace, threshold=threshold)
        return await self._premium_then_free(premium, free)

    async def speed_distribution(
        self, driver: str | None = None, *, bins: int = 20
    ) -> pl.DataFrame:
        premium = (
            functools.partial(self._premium.speed_distribution, driver)
            if self._premium is not None
            else None
        )
        free = functools.partial(self._raw.speed_distribution, driver, bins=bins)
        return await self._premium_then_free(premium, free)

    # Two-driver comparisons: premium only covers each drivers' *fastest* lap (per
    # T1API's docs), so an explicit lap1/lap2 always uses local compute directly.

    async def compare(
        self, driver1: str, driver2: str, *, lap1: int | None = None, lap2: int | None = None
    ) -> pl.DataFrame:
        use_premium = self._premium is not None and lap1 is None and lap2 is None
        premium = (
            functools.partial(self._premium.compare, driver1, driver2) if use_premium else None
        )
        free = functools.partial(self._raw.compare, driver1, driver2, lap1=lap1, lap2=lap2)
        return await self._premium_then_free(premium, free)

    async def throttle_comparison(
        self, driver1: str, driver2: str, *, lap1: int | None = None, lap2: int | None = None
    ) -> pl.DataFrame:
        use_premium = self._premium is not None and lap1 is None and lap2 is None
        premium = (
            functools.partial(self._premium.throttle_comparison, driver1, driver2)
            if use_premium
            else None
        )
        free = functools.partial(
            self._raw.throttle_comparison, driver1, driver2, lap1=lap1, lap2=lap2
        )
        return await self._premium_then_free(premium, free)

    async def lap_time_analysis(
        self, driver1: str, driver2: str, *, lap1: int | None = None, lap2: int | None = None
    ) -> pl.DataFrame:
        use_premium = self._premium is not None and lap1 is None and lap2 is None
        premium = (
            functools.partial(self._premium.lap_time_analysis, driver1, driver2)
            if use_premium
            else None
        )
        free = functools.partial(
            self._raw.lap_time_analysis, driver1, driver2, lap1=lap1, lap2=lap2
        )
        return await self._premium_then_free(premium, free)

    async def track_dominance(
        self,
        driver1: str,
        driver2: str,
        *,
        lap1: int | None = None,
        lap2: int | None = None,
        n_minisectors: int = 25,
    ) -> pl.DataFrame:
        use_premium = self._premium is not None and lap1 is None and lap2 is None
        premium = (
            functools.partial(self._premium.track_dominance, driver1, driver2)
            if use_premium
            else None
        )
        free = functools.partial(
            self._raw.track_dominance,
            driver1,
            driver2,
            lap1=lap1,
            lap2=lap2,
            n_minisectors=n_minisectors,
        )
        return await self._premium_then_free(premium, free)

    # -- laps/results/weather/messages: always the free F1 engine -------------
    #
    # T1API has no raw parity endpoints for these (only derived analysis, which is
    # Module 5 territory), so — like telemetry — they're never routed to premium.

    async def load(
        self,
        *,
        laps: bool = True,
        telemetry: bool = True,
        weather: bool = True,
        messages: bool = True,
    ) -> AsyncSession:
        """Prefetch the requested stream groups concurrently.

        Optional: every accessor below fetches & caches on first use regardless.
        """
        await self._raw.load(laps=laps, telemetry=telemetry, weather=weather, messages=messages)
        return self

    async def laps(self) -> LapsFrame:
        return LapsFrame(await self._raw.laps())

    async def results(self) -> pl.DataFrame:
        return await self._raw.results()

    async def weather(self) -> pl.DataFrame:
        return await self._raw.weather()

    async def race_control_messages(self) -> pl.DataFrame:
        return await self._raw.race_control_messages()

    async def track_status(self) -> pl.DataFrame:
        return await self._raw.track_status()

    async def session_status(self) -> pl.DataFrame:
        return await self._raw.session_status()

    async def total_laps(self) -> int | None:
        return await self._raw.total_laps()


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

    @property
    def last_source(self) -> str | None:
        return self._inner.last_source

    def telemetry(self, driver: str) -> pl.DataFrame:
        return self._loop.run(self._inner.telemetry(driver))

    def lap_telemetry(self, driver: str, lap_number: int) -> pl.DataFrame:
        return self._loop.run(self._inner.lap_telemetry(driver, lap_number))

    def driver_ahead(self, driver: str) -> pl.DataFrame:
        return self._loop.run(self._inner.driver_ahead(driver))

    def top_speeds(self) -> pl.DataFrame:
        return self._loop.run(self._inner.top_speeds())

    def speed_trap_top_speeds(self) -> pl.DataFrame:
        return self._loop.run(self._inner.speed_trap_top_speeds())

    def tyre_stints(self) -> pl.DataFrame:
        return self._loop.run(self._inner.tyre_stints())

    def qualifying_results(self) -> pl.DataFrame:
        return self._loop.run(self._inner.qualifying_results())

    def driver_pace(self, *, threshold: float = 1.07) -> pl.DataFrame:
        return self._loop.run(self._inner.driver_pace(threshold=threshold))

    def teams_pace(self, *, threshold: float = 1.07) -> pl.DataFrame:
        return self._loop.run(self._inner.teams_pace(threshold=threshold))

    def speed_distribution(self, driver: str | None = None, *, bins: int = 20) -> pl.DataFrame:
        return self._loop.run(self._inner.speed_distribution(driver, bins=bins))

    def compare(
        self, driver1: str, driver2: str, *, lap1: int | None = None, lap2: int | None = None
    ) -> pl.DataFrame:
        return self._loop.run(self._inner.compare(driver1, driver2, lap1=lap1, lap2=lap2))

    def throttle_comparison(
        self, driver1: str, driver2: str, *, lap1: int | None = None, lap2: int | None = None
    ) -> pl.DataFrame:
        return self._loop.run(
            self._inner.throttle_comparison(driver1, driver2, lap1=lap1, lap2=lap2)
        )

    def lap_time_analysis(
        self, driver1: str, driver2: str, *, lap1: int | None = None, lap2: int | None = None
    ) -> pl.DataFrame:
        return self._loop.run(self._inner.lap_time_analysis(driver1, driver2, lap1=lap1, lap2=lap2))

    def track_dominance(
        self,
        driver1: str,
        driver2: str,
        *,
        lap1: int | None = None,
        lap2: int | None = None,
        n_minisectors: int = 25,
    ) -> pl.DataFrame:
        return self._loop.run(
            self._inner.track_dominance(
                driver1, driver2, lap1=lap1, lap2=lap2, n_minisectors=n_minisectors
            )
        )

    def load(
        self,
        *,
        laps: bool = True,
        telemetry: bool = True,
        weather: bool = True,
        messages: bool = True,
    ) -> Session:
        self._loop.run(
            self._inner.load(laps=laps, telemetry=telemetry, weather=weather, messages=messages)
        )
        return self

    def laps(self) -> LapsFrame:
        return self._loop.run(self._inner.laps())

    def results(self) -> pl.DataFrame:
        return self._loop.run(self._inner.results())

    def weather(self) -> pl.DataFrame:
        return self._loop.run(self._inner.weather())

    def race_control_messages(self) -> pl.DataFrame:
        return self._loop.run(self._inner.race_control_messages())

    def track_status(self) -> pl.DataFrame:
        return self._loop.run(self._inner.track_status())

    def session_status(self) -> pl.DataFrame:
        return self._loop.run(self._inner.session_status())

    def total_laps(self) -> int | None:
        return self._loop.run(self._inner.total_laps())
