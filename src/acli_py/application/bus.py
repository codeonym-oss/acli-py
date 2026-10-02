"""The bus every front end sends its queries and commands through.

Around the handlers sit four behaviors (see `acli_py.application.behaviors`):

- `Activity` (outermost) counts what is in flight and records every message, its duration
  and outcome, for the TUI's spinner and activity log;
- `QueryCache` answers a repeated query from memory for a short while;
- `Confirm` asks the user before a command changes anything;
- `Announce` publishes `IssueChanged` after each command that touched an issue; its
  subscribers empty the cache, keep the audit log and tell the screens.

`bulk` runs one kind of command over many issues, asking once (`acli_py.application.bulk`),
and `trail` keeps each run in the audit log.

The bus does not know its handlers: the composition root (`acli_py.bootstrap`) registers them
on the mediator before handing it over.
"""

from __future__ import annotations

from typing import Any, TypeVar

from mediary import Mediator, Stream
from mediary.cqrs import StreamQuery

from acli_py.application.audit import AuditTrail
from acli_py.application.behaviors import CACHE_SECONDS, Activity, Announce, Confirm, QueryCache
from acli_py.application.bulk import Bulk
from acli_py.application.events.issue_changed.subscribers import Screens
from acli_py.application.ports import AuditLog, Confirmer, CurrentSite

T = TypeVar("T")


class Bus:
    """The mediator, with the application's behaviors, working on one site."""

    def __init__(
        self,
        mediator: Mediator,
        site: CurrentSite,
        audit: AuditLog,
        *,
        confirmer: Confirmer | None = None,
        assume_yes: bool = False,
        cache_seconds: float = CACHE_SECONDS,
    ) -> None:
        self.site = site
        self.mediator = mediator
        self.activity = Activity()
        self.cache = QueryCache(cache_seconds)
        self.confirm = Confirm(confirmer, lambda: site.dry_run, assume_yes=assume_yes)
        self.listeners = Screens()
        self.trail = AuditTrail(audit)
        self.bulk = Bulk(self.send, self.confirm, self.trail, lambda: site.dry_run)
        mediator.use(self.activity, order=-100)
        mediator.use(self.cache, kinds={"query"}, order=0)
        mediator.use(self.confirm, kinds={"command"}, order=-50)
        mediator.use(Announce(mediator, lambda: site.dry_run), kinds={"command"}, order=0)

    async def send(self, message: Any) -> Any:
        """Send a query or command and return its result."""
        return await self.mediator.send(message)

    def stream(self, query: StreamQuery[T]) -> Stream[T]:
        """Stream the items a stream query's handler yields, as they come."""
        return self.mediator.stream(query)
