from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.get_sprint.view import SprintView


@query
@dataclass(frozen=True)
class GetSprint(Query[SprintView]):
    """Sprint `sprint_id`."""

    sprint_id: int
