from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Filters
from acli_py.application.queries.list_filter_columns.query import ListFilterColumns
from acli_py.application.queries.list_filter_columns.view import FilterColumnsView


@query_handler
def list_filter_columns(request: ListFilterColumns, filters: Filters) -> FilterColumnsView:
    """Read the columns."""
    return FilterColumnsView(tuple(filters.columns(request.filter_id.strip())))
