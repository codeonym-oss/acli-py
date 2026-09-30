"""After a command succeeds: publish `IssueChanged`, with what changed when it says."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mediary import Mediator, Next

from acli_py.application.changes import Changed
from acli_py.application.events.issue_changed.event import IssueChanged


class Announce:
    """Runs a command, then tells the event's subscribers (cache, audit log, screens)."""

    def __init__(self, mediator: Mediator, dry_run: Callable[[], bool]) -> None:
        self.mediator = mediator
        self.dry_run = dry_run

    async def handle(self, message: object, next: Next[Any], /) -> Any:
        """Run the command, then announce it."""
        result = await next()
        what, dry_run = type(message).__name__, self.dry_run()
        if isinstance(result, Changed):
            change = IssueChanged(result.key, what, dry_run, result.before, result.after)
        else:
            key = getattr(message, "key", None) or (result if isinstance(result, str) else "")
            change = IssueChanged(str(key), what, dry_run)
        await self.mediator.publish(change)
        return result
