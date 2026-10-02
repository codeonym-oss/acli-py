from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import SiteLists
from acli_py.application.queries.list_priorities.query import ListPriorities
from acli_py.application.queries.list_priorities.view import NamedView


@query_handler
def list_priorities(request: ListPriorities, lists: SiteLists) -> NamedView:
    """Read the priorities."""
    return NamedView(tuple(lists.priorities()))
