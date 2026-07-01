"""A background event-loop thread that lets the sync facade drive the async core.

Running every sync call through one persistent loop keeps the ``httpx.AsyncClient``
connection pools bound to a single event loop (reusing them across calls), which a
fresh ``asyncio.run`` per call would not.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

_T = TypeVar("_T")


class LoopThread:
    """Owns a daemon thread running a dedicated asyncio event loop."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="t1f1-loop", daemon=True
        )
        self._thread.start()

    def run(self, coro: Coroutine[Any, Any, _T]) -> _T:
        """Submit a coroutine to the loop thread and block for its result."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def close(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        if not self._loop.is_closed():
            self._loop.close()
