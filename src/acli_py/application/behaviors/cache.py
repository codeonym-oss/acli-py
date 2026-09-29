"""Answers a repeated query from memory for a short while, so moving through a list is instant."""

from __future__ import annotations

import time
from typing import Any

from mediary import Next

CACHE_SECONDS = 60.0


class QueryCache:
    """Answers a query from memory if the same one succeeded in the last `seconds`."""

    def __init__(self, seconds: float = CACHE_SECONDS) -> None:
        self.seconds = seconds
        self.answers: dict[object, tuple[float, Any]] = {}

    def clear(self) -> None:
        """Forget every answer."""
        self.answers.clear()

    async def handle(self, message: object, next: Next[Any], /) -> Any:
        """Return a fresh cached answer, or ask the handler and keep its answer."""
        hit = self.answers.get(message)
        if hit and time.monotonic() - hit[0] < self.seconds:
            return hit[1]
        result = await next()
        self.answers[message] = (time.monotonic(), result)
        return result
