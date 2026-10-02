from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.get_filter.view import FilterView


@query
@dataclass(frozen=True)
class GetFilter(Query[FilterView]):
    """Filter `filter_id`, with who it is shared with."""

    filter_id: str
