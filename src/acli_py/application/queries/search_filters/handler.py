from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Filters, People
from acli_py.application.queries.list_filters.view import FiltersView
from acli_py.application.queries.search_filters.query import SearchFilters


@query_handler
def search_filters(request: SearchFilters, filters: Filters, people: People) -> FiltersView:
    """Find the filters."""
    found = filters.search(
        name=request.name,
        owner=people.account_id(request.owner) if request.owner else None,
        project=request.project.strip().upper() if request.project else None,
        limit=request.limit,
    )
    return FiltersView(tuple(found))
