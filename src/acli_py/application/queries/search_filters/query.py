from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_filters.view import FiltersView


@query
@dataclass(frozen=True)
class SearchFilters(Query[FiltersView]):
    """Up to `limit` filters (None: all) by `name`, `owner` ('@me', an email), `project`."""

    name: str | None = None
    owner: str | None = None
    project: str | None = None
    limit: int | None = 50
