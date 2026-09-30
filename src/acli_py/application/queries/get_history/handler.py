from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import IssueReader
from acli_py.application.queries.get_history.query import GetHistory
from acli_py.application.queries.get_history.view import HistoryRow, HistoryView


@query_handler
def get_history(request: GetHistory, issues: IssueReader) -> HistoryView:
    """Read the changelog, and flatten it to one row per field changed."""
    key = request.key.strip().upper()
    rows = [
        HistoryRow(entry.id, entry.at, entry.author, change)
        for entry in issues.history(key)
        for change in entry.changes
        if not request.field or change.about(request.field)
    ]
    if request.newest_first:
        rows.reverse()
    return HistoryView(key, tuple(rows[: request.limit]))
