from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_filter_columns.view import FilterColumnsView


@query
@dataclass(frozen=True)
class ListFilterColumns(Query[FilterColumnsView]):
    """The columns filter `filter_id` shows."""

    filter_id: str
