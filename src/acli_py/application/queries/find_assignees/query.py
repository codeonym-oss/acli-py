from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.find_assignees.view import AssigneesView


@query
@dataclass(frozen=True)
class FindAssignees(Query[AssigneesView]):
    """People (not apps) who can be assigned issue `key`, matching a name or email."""

    key: str
    text: str = ""
