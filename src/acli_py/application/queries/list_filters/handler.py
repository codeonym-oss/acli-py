from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Filters
from acli_py.application.queries.list_filters.query import ListFilters
from acli_py.application.queries.list_filters.view import FiltersView


@query_handler
def list_filters(request: ListFilters, filters: Filters) -> FiltersView:
    """Read the filters."""
    return FiltersView(tuple(filters.favourites() if request.favourites else filters.mine()))
