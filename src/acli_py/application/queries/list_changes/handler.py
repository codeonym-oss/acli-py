from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.changes import undone_by
from acli_py.application.ports import AuditLog
from acli_py.application.queries.list_changes.query import ListChanges
from acli_py.application.queries.list_changes.view import ChangesView


@query_handler
def list_changes(request: ListChanges, audit: AuditLog) -> ChangesView:
    """Read the log, and which records later undos reversed."""
    entries = audit.entries()
    newest = tuple(reversed(entries))
    return ChangesView(newest[: request.limit] if request.limit else newest, undone_by(entries))
