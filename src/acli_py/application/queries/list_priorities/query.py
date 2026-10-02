from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_priorities.view import NamedView


@query
@dataclass(frozen=True)
class ListPriorities(Query[NamedView]):
    """The priorities, highest first."""
