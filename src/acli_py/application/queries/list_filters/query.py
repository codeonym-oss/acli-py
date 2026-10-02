from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_filters.view import FiltersView


@query
@dataclass(frozen=True)
class ListFilters(Query[FiltersView]):
    """The user's own filters, or (`favourites`) the ones they starred."""

    favourites: bool = False
