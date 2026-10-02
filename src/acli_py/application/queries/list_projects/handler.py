from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Projects
from acli_py.application.queries.list_projects.query import ListProjects
from acli_py.application.queries.list_projects.view import ProjectsView


@query_handler
def list_projects(request: ListProjects, projects: Projects) -> ProjectsView:
    """Read the projects."""
    if request.recent:
        return ProjectsView(tuple(projects.recent()))
    found = projects.projects(query=request.query, status=request.status, limit=request.limit)
    if not request.recent_first:
        return ProjectsView(tuple(found))
    recent = projects.recent()
    seen = {p.key for p in recent}
    return ProjectsView((*recent, *(p for p in found if p.key not in seen)))
