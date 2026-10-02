from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Boards
from acli_py.application.queries.issue_columns import columns, jira_fields
from acli_py.application.queries.list_backlog.query import ListBacklog
from acli_py.application.queries.search_issues.view import IssuesView


@query_handler
def list_backlog(request: ListBacklog, boards: Boards) -> IssuesView:
    """Fetch the backlog, with the fields its columns need."""
    shown = columns(request.fields)
    found = boards.backlog(request.board_id, request.jql, jira_fields(shown), limit=request.limit)
    return IssuesView(request.jql or "", tuple(found), shown)
