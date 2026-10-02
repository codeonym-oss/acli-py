from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Projects
from acli_py.application.queries.get_project.query import GetProject
from acli_py.application.queries.get_project.view import ProjectView


@query_handler
def get_project(request: GetProject, projects: Projects) -> ProjectView:
    """Read the project."""
    return ProjectView(projects.project(request.key.strip().upper()))
