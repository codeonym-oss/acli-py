from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Projects
from acli_py.application.queries.list_components.query import ListComponents
from acli_py.application.queries.list_components.view import ComponentsView


@query_handler
def list_components(request: ListComponents, projects: Projects) -> ComponentsView:
    """Read the components."""
    key = request.key.strip().upper()
    return ComponentsView(key, tuple(projects.components(key)))
