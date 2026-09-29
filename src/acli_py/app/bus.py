"""The mediator the TUI and the shell send their queries and commands through.

Around the handlers sit three behaviors:

- `Activity` (outermost) counts what is in flight and records every message, its duration
  and outcome, for the TUI's spinner and activity log;
- `QueryCache` answers a repeated query from memory for a short while;
- `Announce` publishes `IssueChanged` after each command that touched an issue, and empties the
  cache, so the next read sees the change.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from mediary import Mediator, Next

from acli_py.app import handlers
from acli_py.app.messages import IssueChanged
from acli_py.app.site import Site
from acli_py.client import JiraClient

T = TypeVar("T")
CACHE_SECONDS = 60.0


class SiteResolver:
    """Hands the handlers their `Site` (and builds anything else the default way)."""

    def __init__(self, site: Site) -> None:
        self.site = site

    def resolve(self, cls: type[T], /) -> T:
        """Return the site for `Site` and the client for `JiraClient`, else `cls()`."""
        if cls is Site:
            return self.site  # type: ignore[return-value]
        if cls is JiraClient:
            return self.site.client  # type: ignore[return-value]
        return cls()


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


class Announce:
    """After a command succeeds: empty the cache and publish `IssueChanged`."""

    def __init__(self, bus: Bus) -> None:
        self.bus = bus

    async def handle(self, message: object, next: Next[Any], /) -> Any:
        """Run the command, then announce it."""
        result = await next()
        self.bus.cache.clear()
        key = getattr(message, "key", None) or (result if isinstance(result, str) else "")
        await self.bus.mediator.publish(
            IssueChanged(str(key), type(message).__name__, self.bus.site.dry_run)
        )
        return result


def describe(message: object) -> str:
    """Return a short, readable account of a message for the activity log."""
    parts = []
    for name, value in vars(message).items():
        if value in (None, "", (), False):
            continue
        text = str(value)
        parts.append(f"{name}={text[:60] + '…' if len(text) > 60 else text}")
    return " ".join(parts)


class Bus:
    """The mediator, wired to one site."""

    def __init__(self, site: Site, *, cache_seconds: float = CACHE_SECONDS) -> None:
        self.site = site
        self.activity = Activity()
        self.cache = QueryCache(cache_seconds)
        self.mediator = Mediator(resolver=SiteResolver(site))
        self.mediator.scan(handlers)
        self.mediator.use(self.activity, order=-100)
        self.mediator.use(self.cache, kinds={"query"}, order=0)
        self.mediator.use(Announce(self), kinds={"command"}, order=0)
        self.listeners: list[Callable[[IssueChanged], Any]] = []
        self.mediator.register(IssueChanged, self._on_change)

    async def _on_change(self, change: IssueChanged) -> None:
        for listener in list(self.listeners):
            outcome = listener(change)
            if asyncio.iscoroutine(outcome):
                await outcome

    async def send(self, message: Any) -> Any:
        """Send a query or command and return its result."""
        return await self.mediator.send(message)
