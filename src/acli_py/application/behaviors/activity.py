"""Counts messages in flight and keeps a log of the latest ones (the TUI's spinner and log)."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mediary import Next


@dataclass(frozen=True)
class Entry:
    """One message the bus handled."""

    at: float
    name: str
    summary: str
    seconds: float
    error: str = ""


class Activity:
    """Counts messages in flight, and keeps the latest ones for the activity log."""

    def __init__(self, keep: int = 200) -> None:
        self.busy = 0
        self.entries: deque[Entry] = deque(maxlen=keep)
        self.listeners: list[Callable[[], None]] = []

    def _changed(self) -> None:
        for listener in list(self.listeners):
            listener()

    async def handle(self, message: object, next: Next[Any], /) -> Any:
        """Track `message` while the rest of the pipeline runs."""
        self.busy += 1
        self._changed()
        started = time.perf_counter()
        error = ""
        try:
            return await next()
        except Exception as caught:
            error = str(caught) or type(caught).__name__
            raise
        finally:
            self.busy -= 1
            self.entries.append(
                Entry(
                    time.time(),
                    type(message).__name__,
                    describe(message),
                    time.perf_counter() - started,
                    error,
                )
            )
            self._changed()


def describe(message: object) -> str:
    """Return a short, readable account of a message for the activity log."""
    parts = []
    for name, value in vars(message).items():
        if value in (None, "", (), False):
            continue
        text = str(value)
        parts.append(f"{name}={text[:60] + '…' if len(text) > 60 else text}")
    return " ".join(parts)
