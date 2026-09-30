"""What happens after an issue changes.

Subscribers run in name order, so the cache is dropped before the screens ask again.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from mediary.cqrs import event_handler

from acli_py.application.audit import AuditTrail
from acli_py.application.behaviors.cache import QueryCache
from acli_py.application.changes import Changed
from acli_py.application.events.issue_changed.event import IssueChanged


class Screens(list[Callable[[IssueChanged], Any]]):
    """What wants to hear about changes: the TUI's refresh, mostly. Listeners may be async."""


@event_handler
def drop_cached_answers(change: IssueChanged, cache: QueryCache) -> None:
    """Forget every cached answer, so the next read sees the change."""
    cache.clear()


@event_handler
def record_in_audit_log(change: IssueChanged, trail: AuditTrail) -> None:
    """Keep the change, with what it replaced; a dry run changed nothing, so it is not kept."""
    if not change.dry_run:
        trail.note(change.what, Changed(change.key, change.before, change.after))


@event_handler
async def tell_screens(change: IssueChanged, screens: Screens) -> None:
    """Tell each listener, in turn."""
    for listener in list(screens):
        outcome = listener(change)
        if asyncio.iscoroutine(outcome):
            await outcome
