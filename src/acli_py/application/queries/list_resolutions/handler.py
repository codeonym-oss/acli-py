from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import SiteLists
from acli_py.application.queries.list_priorities.view import NamedView
from acli_py.application.queries.list_resolutions.query import ListResolutions


@query_handler
def list_resolutions(request: ListResolutions, lists: SiteLists) -> NamedView:
    """Read the resolutions."""
    return NamedView(tuple(lists.resolutions()))
