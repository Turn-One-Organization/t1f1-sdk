"""Client configuration: base URLs, timeouts, retry policy, and HTTP headers."""

from __future__ import annotations

from dataclasses import dataclass, field

#: Official F1 live-timing static feed (free tier).
F1_LIVETIMING_BASE_URL = "https://livetiming.formula1.com/static/"

#: Proprietary T1API base (premium tier).
T1API_BASE_URL = "https://api.t1f1.com"

#: Browser-like headers required to fetch from the F1 CDN without being blocked.
_DEFAULT_F1_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.formula1.com",
    "Referer": "https://www.formula1.com/",
}


@dataclass(frozen=True)
class ClientConfig:
    """Immutable configuration shared across a client and its transports.

    ``f1_base_url`` may point at a proxy (e.g. a Cloudflare Worker) that mirrors the
    F1 CDN — this mirrors the backend's ``F1_PROXY_BASE_URL`` support.
    """

    f1_base_url: str = F1_LIVETIMING_BASE_URL
    t1api_base_url: str = T1API_BASE_URL
    timeout: float = 30.0
    max_retries: int = 3
    backoff_base: float = 0.5
    #: Cap on how long we will honour a server-provided ``Retry-After`` before giving up.
    max_retry_after: float = 10.0
    f1_headers: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_F1_HEADERS))

    def f1_url(self, path: str) -> str:
        """Join a path onto the (proxy-aware, trailing-slash-normalised) F1 base URL."""
        return self.f1_base_url.rstrip("/") + "/" + path.lstrip("/")

    def t1api_url(self, path: str) -> str:
        """Join a path onto the T1API base URL."""
        return self.t1api_base_url.rstrip("/") + "/" + path.lstrip("/")
