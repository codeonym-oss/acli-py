from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Worklogs
from acli_py.application.queries.list_worklogs.query import ListWorklogs
from acli_py.application.queries.list_worklogs.view import WorklogsView


@query_handler
def list_worklogs(request: ListWorklogs, worklogs: Worklogs) -> WorklogsView:
    """Read the worklogs."""
    key = request.key.strip().upper()
    return WorklogsView(key, tuple(worklogs.worklogs(key)))
