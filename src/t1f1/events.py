"""Season event schedule from the F1 static feed's ``Index.json``.

Free tier only, deliberately: T1API's ``/api/v2/seasons/{year}/events`` proxies the
same upstream source but drops session start/end dates (per its own docs), so
routing to it would be a *worse* result than reconstructing from ``Index.json``
directly — unlike Module 2's laps/results/weather, there's no premium upside here.

**Known, confirmed-live limitation** (see ``ingestion.resolver``'s module docstring
for the full explanation): a past season's ``Index.json`` may not list every round —
2024's currently only has 15 of 24, missing Bahrain through Monaco — so
``get_event_schedule()`` can silently under-report a season, and ``"round"`` is a
*positional* index into what's actually present, not the real FIA round number.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import polars as pl

from t1f1.config import ClientConfig
from t1f1.exceptions import SessionNotFoundError
from t1f1.ingestion.resolver import _resolve_meeting
from t1f1.schemas import EVENT_SCHEMA, EVENT_SESSION_SCHEMA, empty_event_sessions, empty_events
from t1f1.transport import AsyncTransport


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an ``Index.json`` date. These are naive local-circuit times (no ``Z``/
    offset), unlike CarData/Position's UTC ``Utc`` fields — kept naive rather than
    guessing a timezone."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _decode_meetings(meetings: list[dict[str, Any]]) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, meeting in enumerate(meetings, start=1):
        sessions = meeting.get("Sessions", [])
        starts = [d for s in sessions if (d := _parse_datetime(s.get("StartDate")))]
        ends = [d for s in sessions if (d := _parse_datetime(s.get("EndDate")))]
        country = meeting.get("Country")
        rows.append(
            {
                "round": index,
                "event_key": str(meeting.get("Key", "")),
                "name": meeting.get("Name"),
                "official_name": meeting.get("OfficialName", meeting.get("Name")),
                "location": meeting.get("Location"),
                "country": country.get("Name") if isinstance(country, dict) else country,
                "start_date": min(starts) if starts else None,
                "end_date": max(ends) if ends else None,
            }
        )
    if not rows:
        return empty_events()
    return pl.DataFrame(rows, schema=EVENT_SCHEMA)


async def _fetch_meetings(
    transport: AsyncTransport, config: ClientConfig, year: int
) -> list[dict[str, Any]]:
    index = await transport.get_json(config.f1_url(f"{year}/Index.json"))
    meetings = index.get("Meetings", []) if isinstance(index, dict) else []
    if not meetings:
        raise SessionNotFoundError(year=year, reason=f"No meetings published for {year}")
    return meetings


async def get_event_schedule(
    transport: AsyncTransport, config: ClientConfig, year: int
) -> pl.DataFrame:
    """All events (Grand Prix weekends) for ``year``."""
    meetings = await _fetch_meetings(transport, config, year)
    return _decode_meetings(meetings)


async def get_event(
    transport: AsyncTransport, config: ClientConfig, year: int, gp: int | str
) -> dict[str, Any]:
    """One event, by round number, event key, or fuzzy name/location."""
    meetings = await _fetch_meetings(transport, config, year)
    round_number, meeting = _resolve_meeting(meetings, gp, year)
    row = _decode_meetings([meeting]).row(0, named=True)
    # _decode_meetings numbers rounds by position in the list it's given (1 here,
    # since we only passed the one resolved meeting) — restore the real round.
    return {**row, "round": round_number}


async def get_events_remaining(
    transport: AsyncTransport, config: ClientConfig, year: int, *, after: datetime | None = None
) -> pl.DataFrame:
    """Events whose end date is still in the future (default: now)."""
    schedule = await get_event_schedule(transport, config, year)
    if schedule.is_empty():
        return schedule
    cutoff = after or datetime.now()
    return schedule.filter(pl.col("end_date") >= cutoff)


async def get_event_sessions(
    transport: AsyncTransport, config: ClientConfig, year: int, gp: int | str
) -> pl.DataFrame:
    """Sessions (FP1/Q/R/...) for one event, with their ``Index.json`` paths."""
    meetings = await _fetch_meetings(transport, config, year)
    round_number, meeting = _resolve_meeting(meetings, gp, year)
    rows: list[dict[str, Any]] = [
        {
            "round": round_number,
            "session_name": session.get("Name"),
            "session_type": session.get("Type"),
            "start_date": _parse_datetime(session.get("StartDate")),
            "path": session.get("Path"),
        }
        for session in meeting.get("Sessions", [])
    ]
    if not rows:
        return empty_event_sessions()
    return pl.DataFrame(rows, schema=EVENT_SESSION_SCHEMA)
