"""What happens after an issue changes.

Subscribers run in name order, so the cache is dropped before the screens ask again.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from mediary.cqrs import event_handler

from acli_py.application.behaviors.cache import QueryCache
from acli_py.application.changes import AuditRecord
from acli_py.application.events.issue_changed.event import IssueChanged
from acli_py.application.ports import AuditLog


class Screens(list[Callable[[IssueChanged], Any]]):
    """What wants to hear about changes: the TUI's refresh, mostly. Listeners may be async."""


@event_handler
def drop_cached_answers(change: IssueChanged, cache: QueryCache) -> None:
    """Forget every cached answer, so the next read sees the change."""
    cache.clear()


@event_handler
def record_in_audit_log(change: IssueChanged, audit: AuditLog) -> None:
    """Keep the change, with what it replaced; a dry run changed nothing, so it is not kept."""
    if change.dry_run:
        return
    audit.record(
        AuditRecord(change.what, (change.key,), change.before, change.after, datetime.now(UTC))
    )


@event_handler
async def tell_screens(change: IssueChanged, screens: Screens) -> None:
    """Tell each listener, in turn."""
    for listener in list(screens):
        outcome = listener(change)
        if asyncio.iscoroutine(outcome):
            await outcome
