from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.create_sprint.command import CreateSprint
from acli_py.application.ports import Sprints


@command_handler
def create_sprint(request: CreateSprint, sprints: Sprints) -> Changed:
    """Create the sprint; `after` names it."""
    sprint_id = sprints.create(
        request.board_id, request.name, request.start, request.end, request.goal
    )
    return Changed(f"sprint {sprint_id}", after={"sprint": sprint_id, "name": request.name})
