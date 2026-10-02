from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.get_project.view import ProjectView


@query
@dataclass(frozen=True)
class GetProject(Query[ProjectView]):
    """Project `key`, with its lead, issue types, components and versions."""

    key: str
