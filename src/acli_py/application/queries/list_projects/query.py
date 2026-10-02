from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_projects.view import ProjectsView


@query
@dataclass(frozen=True)
class ListProjects(Query[ProjectsView]):
    """Up to `limit` projects (None: all) whose key or name match `query`, by key.

    `status` is 'live', 'archived' or 'deleted' (in the trash). `recent` lists only the ones
    the user viewed lately; `recent_first` lists those first, then the rest.
    """

    query: str | None = None
    status: str = "live"
    limit: int | None = 50
    recent: bool = False
    recent_first: bool = False
