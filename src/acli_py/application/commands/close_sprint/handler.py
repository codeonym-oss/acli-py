from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.close_sprint.command import CloseSprint
from acli_py.application.ports import Sprints
from acli_py.domain.agile import SprintState


@command_handler
def close_sprint(request: CloseSprint, sprints: Sprints) -> Changed:
    """Close the sprint."""
    sprints.update(request.sprint_id, state=SprintState.CLOSED)
    return Changed(request.item, after={"state": SprintState.CLOSED.value})
