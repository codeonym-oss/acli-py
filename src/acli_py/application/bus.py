"""The bus every front end sends its queries and commands through.

Around the handlers sit three behaviors (see `acli_py.application.behaviors`):

- `Activity` (outermost) counts what is in flight and records every message, its duration
  and outcome, for the TUI's spinner and activity log;
- `QueryCache` answers a repeated query from memory for a short while;
- `Announce` publishes `IssueChanged` after each command that touched an issue, and empties the
  cache, so the next read sees the change.

The bus does not know its handlers: the composition root (`acli_py.bootstrap`) registers them
on the mediator before handing it over.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from mediary import Mediator

from acli_py.application.behaviors import CACHE_SECONDS, Activity, Announce, QueryCache
from acli_py.application.messages import IssueChanged
from acli_py.application.site import Site


class Bus:
    """The mediator, with the application's behaviors, working on one site."""

    def __init__(
        self, mediator: Mediator, site: Site, *, cache_seconds: float = CACHE_SECONDS
    ) -> None:
        self.site = site
        self.mediator = mediator
        self.activity = Activity()
        self.cache = QueryCache(cache_seconds)
        mediator.use(self.activity, order=-100)
        mediator.use(self.cache, kinds={"query"}, order=0)
        announce = Announce(self.cache, mediator, lambda: site.dry_run)
        mediator.use(announce, kinds={"command"}, order=0)
        self.listeners: list[Callable[[IssueChanged], Any]] = []
        mediator.register(IssueChanged, self._on_change)

    async def _on_change(self, change: IssueChanged) -> None:
        for listener in list(self.listeners):
            outcome = listener(change)
            if asyncio.iscoroutine(outcome):
                await outcome

    async def send(self, message: Any) -> Any:
        """Send a query or command and return its result."""
        return await self.mediator.send(message)
