"""After a command succeeds: empty the query cache and publish `IssueChanged`."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mediary import Mediator, Next

from acli_py.application.behaviors.cache import QueryCache
from acli_py.application.messages import IssueChanged


class Announce:
    """Runs a command, then drops cached answers and tells subscribers what changed."""

    def __init__(self, cache: QueryCache, mediator: Mediator, dry_run: Callable[[], bool]) -> None:
        self.cache = cache
        self.mediator = mediator
        self.dry_run = dry_run

    async def handle(self, message: object, next: Next[Any], /) -> Any:
        """Run the command, then announce it."""
        result = await next()
        self.cache.clear()
        key = getattr(message, "key", None) or (result if isinstance(result, str) else "")
        await self.mediator.publish(IssueChanged(str(key), type(message).__name__, self.dry_run()))
        return result
