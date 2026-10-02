from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.move_to_sprint.command import MoveToSprint
from acli_py.application.ports import Sprints


@command_handler
def move_to_sprint(request: MoveToSprint, sprints: Sprints) -> Changed:
    """Move the issue."""
    key = request.key.strip().upper()
    sprints.move((key,), request.sprint_id)
    return Changed(key, after={"sprint": request.sprint_id})
