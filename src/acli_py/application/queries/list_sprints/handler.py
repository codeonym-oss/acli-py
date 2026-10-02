from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Sprints
from acli_py.application.queries.list_sprints.query import ListSprints
from acli_py.application.queries.list_sprints.view import SprintsView


@query_handler
def list_sprints(request: ListSprints, sprints: Sprints) -> SprintsView:
    """Read the sprints."""
    found = sprints.sprints(request.board_id, request.states, limit=request.limit)
    return SprintsView(tuple(found))
