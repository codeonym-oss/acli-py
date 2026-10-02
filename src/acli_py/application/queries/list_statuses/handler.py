from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import SiteLists
from acli_py.application.queries.list_statuses.query import ListStatuses
from acli_py.application.queries.list_statuses.view import StatusesView


@query_handler
def list_statuses(request: ListStatuses, lists: SiteLists) -> StatusesView:
    """Read the statuses."""
    return StatusesView(tuple(lists.statuses()))
