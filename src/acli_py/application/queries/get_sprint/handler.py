from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Sprints
from acli_py.application.queries.get_sprint.query import GetSprint
from acli_py.application.queries.get_sprint.view import SprintView


@query_handler
def get_sprint(request: GetSprint, sprints: Sprints) -> SprintView:
    """Read the sprint."""
    return SprintView(sprints.sprint(request.sprint_id))
