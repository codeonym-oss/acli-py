from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_statuses.view import StatusesView


@query
@dataclass(frozen=True)
class ListStatuses(Query[StatusesView]):
    """Every status."""
