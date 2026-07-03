"""Resolve ``(year, gp, session)`` to a concrete F1 static-feed session directory.

Ports the season-index scraping and session-alias matching from the backend's
``F1StaticClient`` (``fetch_season_index`` / ``get_event_session_url`` and the
``_SESSION_ALIASES`` normalisation helpers).

The F1 ``Index.json`` lists ``Meetings`` (events); each meeting lists ``Sessions``,
and each session carries a ``Path`` relative to the static base — we use that directly
to build the session directory URL.

**Known, confirmed-live limitation:** for a past season, ``Index.json`` does not
necessarily list *every* round — checked live against 2024, whose ``Index.json``
only retains the final 15 of 24 meetings (starting from the Spanish GP; Bahrain
through Monaco are absent). Since an integer ``gp`` is resolved as a **positional**
index into whatever ``Meetings`` *does* contain (``1 <= gp <= len(meetings)``, not
the real FIA round number), passing an early-season round number for an affected
year silently resolves to the wrong event rather than raising — e.g. ``gp=1`` for
2024 resolves to the Spanish GP, not Bahrain. Prefer event name/key lookups (``gp="Bahrain
Grand Prix"``) over integer round numbers when working with older/partial seasons;
there is currently no cheap way to detect whether a given year's index is complete.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from t1f1.config import ClientConfig
from t1f1.exceptions import SessionNotFoundError
from t1f1.transport import AsyncTransport

#: Human aliases -> canonical session, used for loose, case-insensitive matching.
_SESSION_ALIASES: dict[str, set[str]] = {
    "race": {"r", "race", "grand prix"},
    "qualifying": {"q", "quali", "qualifying"},
    "sprint": {"s", "sprint"},
    "sprint_qualifying": {"sq", "sprint qualifying", "sprint shootout"},
    "practice_1": {"fp1", "p1", "practice 1", "free practice 1"},
    "practice_2": {"fp2", "p2", "practice 2", "free practice 2"},
    "practice_3": {"fp3", "p3", "practice 3", "free practice 3"},
}


@dataclass(frozen=True)
class SessionRef:
    """A fully resolved session location plus its event/session metadata."""

    year: int
    round_number: int
    event_name: str
    official_name: str
    session_name: str
    session_type: str
    base_url: str  # session directory URL, trailing slash included

    def file_url(self, filename: str) -> str:
        return self.base_url.rstrip("/") + "/" + filename


def _normalize_text(value: str) -> str:
    """Lower-case and collapse non-alphanumerics to single spaces."""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _build_session_tokens(value: str) -> set[str]:
    """Token set for a session label, expanded with aliases and its acronym."""
    normalized = _normalize_text(value)
    compact = normalized.replace(" ", "")
    words = [w for w in normalized.split() if w]
    acronym = "".join(word[0] for word in words)

    tokens = {normalized, compact}
    if acronym:
        tokens.add(acronym)

    for aliases in _SESSION_ALIASES.values():
        normalized_aliases = {_normalize_text(alias) for alias in aliases}
        alias_compact = {alias.replace(" ", "") for alias in normalized_aliases}
        if normalized in normalized_aliases or compact in alias_compact or acronym in alias_compact:
            tokens.update(normalized_aliases)
            tokens.update(alias_compact)

    return {token for token in tokens if token}


def _session_matches(requested: str, candidate: str) -> bool:
    """True when two session labels refer to the same F1 session."""
    if _build_session_tokens(requested) & _build_session_tokens(candidate):
        return True
    req = _normalize_text(requested)
    cand = _normalize_text(candidate)
    # Substring fallback only for labels long enough to be unambiguous; short codes
    # like "r"/"q"/"p1" must match via the alias path above.
    if len(req) < 3 or len(cand) < 3:
        return False
    return req in cand or cand in req


def _event_matches(requested: str, meeting: dict[str, Any]) -> bool:
    target = _normalize_text(requested)
    for key in ("Name", "OfficialName", "Location"):
        value = meeting.get(key)
        if not value:
            continue
        candidate = _normalize_text(str(value))
        if target == candidate or target in candidate or candidate in target:
            return True
    return False


def _resolve_meeting(meetings: list[dict[str, Any]], gp: int | str, year: int) -> tuple[int, dict]:
    """Return ``(round_number, meeting)`` for a round number, event key, or name."""
    if isinstance(gp, int):
        if 1 <= gp <= len(meetings):
            return gp, meetings[gp - 1]
        raise SessionNotFoundError(
            year=year,
            gp=gp,
            reason=f"Round {gp} out of range (1-{len(meetings)})",
            valid_rounds=list(range(1, len(meetings) + 1)),
        )

    # String: try numeric event Key, then fuzzy name/location match.
    for index, meeting in enumerate(meetings, start=1):
        if str(meeting.get("Key")) == str(gp):
            return index, meeting
    for index, meeting in enumerate(meetings, start=1):
        if _event_matches(str(gp), meeting):
            return index, meeting

    raise SessionNotFoundError(
        year=year,
        gp=gp,
        reason=f"No event matching {gp!r} in {year}",
        suggestions=[str(m.get("Name")) for m in meetings if m.get("Name")],
    )


async def resolve_session(
    transport: AsyncTransport,
    config: ClientConfig,
    year: int,
    gp: int | str,
    session: str,
) -> SessionRef:
    """Fetch the season index and resolve the concrete session directory."""
    index = await transport.get_json(config.f1_url(f"{year}/Index.json"))
    meetings = index.get("Meetings", []) if isinstance(index, dict) else []
    if not meetings:
        raise SessionNotFoundError(year=year, reason=f"No meetings published for {year}")

    round_number, meeting = _resolve_meeting(meetings, gp, year)
    sessions = meeting.get("Sessions", [])

    for entry in sessions:
        label_name = str(entry.get("Name", ""))
        label_type = str(entry.get("Type", ""))
        if _session_matches(session, label_name) or _session_matches(session, label_type):
            path = entry.get("Path")
            if not path:
                continue
            return SessionRef(
                year=year,
                round_number=round_number,
                event_name=str(meeting.get("Name", "")),
                official_name=str(meeting.get("OfficialName", meeting.get("Name", ""))),
                session_name=label_name or label_type,
                session_type=label_type or label_name,
                base_url=config.f1_url(path),
            )

    raise SessionNotFoundError(
        year=year,
        gp=gp,
        session=session,
        reason=f"Session {session!r} not found for {meeting.get('Name')}",
        suggestions=[str(s.get("Name")) for s in sessions if s.get("Name")],
    )
