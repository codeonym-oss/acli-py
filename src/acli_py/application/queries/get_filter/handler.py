from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Filters
from acli_py.application.queries.get_filter.query import GetFilter
from acli_py.application.queries.get_filter.view import FilterView


@query_handler
def get_filter(request: GetFilter, filters: Filters) -> FilterView:
    """Read the filter."""
    return FilterView(filters.filter(request.filter_id.strip()))
