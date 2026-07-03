"""Exception taxonomy for t1f1.

Mirrors the backend's domain exceptions (``src/core/exceptions.py`` in
TurnOneTelemetry) so error semantics are identical whether data comes from the raw
F1 feed or from ``api.t1f1.com``.
"""

from __future__ import annotations

from collections.abc import Sequence


class T1F1Error(Exception):
    """Base class for every error raised by the SDK."""


class AuthError(T1F1Error):
    """The T1API rejected the API key (HTTP 401/403)."""


class RateLimitError(T1F1Error):
    """The T1API rate limit was exceeded (HTTP 429)."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class SessionNotFoundError(T1F1Error):
    """The requested session does not exist in the schedule (HTTP 404).

    Carries lookup hints so callers can suggest valid alternatives, matching the
    backend's ``session_not_found`` payload.
    """

    def __init__(
        self,
        *,
        year: int | None = None,
        gp: int | str | None = None,
        session: str | None = None,
        reason: str = "",
        valid_rounds: Sequence[int] | None = None,
        suggestions: Sequence[str] | None = None,
    ) -> None:
        self.year = year
        self.gp = gp
        self.session = session
        self.reason = reason
        self.valid_rounds = list(valid_rounds) if valid_rounds else []
        self.suggestions = list(suggestions) if suggestions else []
        detail = reason or f"Session not found: year={year} gp={gp} session={session}"
        super().__init__(detail)


class DataNotAvailableError(T1F1Error):
    """The session exists but no source can supply data yet (HTTP 503).

    Typically the live-timing feed has not been published or is still updating.
    """

    RETRY_AFTER_SECONDS = 300

    def __init__(
        self,
        reason: str = "",
        *,
        year: int | None = None,
        gp: int | str | None = None,
        session: str | None = None,
        sources_tried: Sequence[str] | None = None,
        retry_after: float | None = None,
    ) -> None:
        self.year = year
        self.gp = gp
        self.session = session
        self.sources_tried = list(sources_tried) if sources_tried else []
        self.retry_after = retry_after if retry_after is not None else self.RETRY_AFTER_SECONDS
        super().__init__(reason or "Data not available yet")


class UpstreamUnavailableError(T1F1Error):
    """An upstream dependency (F1 live-timing or T1API) failed (HTTP 5xx / network)."""

    RETRY_AFTER_SECONDS = 60

    def __init__(
        self,
        *,
        source: str,
        reason: str = "",
        retry_after: float | None = None,
    ) -> None:
        self.source = source
        self.reason = reason
        self.retry_after = retry_after if retry_after is not None else self.RETRY_AFTER_SECONDS
        super().__init__(reason or f"Upstream unavailable: {source}")


#: Errors that mean "this particular upstream is having a bad time right now" rather
#: than "the request itself is wrong" — safe to silently retry against a fallback
#: source (premium T1API -> local free-tier compute, or T1API -> Ergast). Deliberately
#: excludes ``AuthError``: a rejected API key is a configuration mistake the caller
#: should see, not something to paper over by quietly degrading to the free tier.
PREMIUM_FALLBACK_ERRORS = (UpstreamUnavailableError, DataNotAvailableError, RateLimitError)
