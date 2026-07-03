"""Anchor the F1 feed's elapsed-time clock strings to absolute UTC.

The feed's ``HH:MM:SS.mmm`` line prefix (used by ``TimingData``, ``TimingAppData``,
``WeatherData``, ``TrackStatus``, ``SessionStatus``, ``RaceControlMessages``) is
**elapsed time since the recording started**, not a wall-clock time-of-day — e.g. the
very first line of a stream is typically ``"00:00:0x.xxx"`` regardless of what time of
day the session actually ran. That's confirmed by CarData/Position, which carry both
this prefix *and* an embedded absolute ``Utc`` field: prefix ``"00:00:01.000"`` lines
up with an embedded ``Utc`` of e.g. ``"...T13:00:01.000Z"`` — the prefix is clearly
relative, not a clock reading. :class:`SessionClock` anchors it by adding the elapsed
duration to the session's absolute UTC start instant (from ``SessionInfo.json``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def parse_elapsed(value: str) -> timedelta | None:
    """Parse a feed clock string (``HH:MM:SS.mmm`` or ``HH:MM:SS``) as elapsed time."""
    text = value.strip()
    if not text:
        return None
    sign = 1
    if text.startswith("-"):
        sign = -1
        text = text[1:]
    parts = text.split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = parts
            total_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        elif len(parts) == 2:
            minutes, seconds = parts
            total_seconds = int(minutes) * 60 + float(seconds)
        else:
            total_seconds = float(parts[0])
    except ValueError:
        return None
    return sign * timedelta(seconds=total_seconds)


def session_start_from_info(info: dict[str, Any]) -> datetime | None:
    """Derive the session's absolute UTC start instant from ``SessionInfo.json``.

    ``StartDate`` is local circuit time; ``GmtOffset`` (local minus UTC) is subtracted
    to land on UTC. Returns ``None`` if either field is missing or unparsable, rather
    than guessing.
    """
    start_date = info.get("StartDate")
    gmt_offset = info.get("GmtOffset")
    if not start_date:
        return None
    try:
        local_dt = datetime.fromisoformat(str(start_date))
    except ValueError:
        return None
    offset = timedelta()
    if gmt_offset:
        text = str(gmt_offset).strip()
        parsed = parse_elapsed(text.lstrip("+-"))
        if parsed is not None:
            offset = -parsed if text.startswith("-") else parsed
    return (local_dt - offset).replace(tzinfo=timezone.utc)


class SessionClock:
    """Converts the feed's elapsed-time clock strings to absolute UTC instants."""

    def __init__(self, start: datetime | None) -> None:
        self._start = start

    def to_utc(self, clock: str | None) -> datetime | None:
        if self._start is None or not clock:
            return None
        elapsed = parse_elapsed(clock)
        if elapsed is None:
            return None
        return self._start + elapsed
