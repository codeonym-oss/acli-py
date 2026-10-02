from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_projects.view import ProjectsView


@query
@dataclass(frozen=True)
class ListBoardProjects(Query[ProjectsView]):
    """Up to `limit` (None: all) of the projects board `board_id` shows."""

    board_id: int
    limit: int | None = 50
