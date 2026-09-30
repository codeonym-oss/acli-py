from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_audiences.view import AudiencesView


@query
@dataclass(frozen=True)
class ListAudiences(Query[AudiencesView]):
    """The roles of `project` a comment can be kept to; without a project, the site's groups."""

    project: str = ""
