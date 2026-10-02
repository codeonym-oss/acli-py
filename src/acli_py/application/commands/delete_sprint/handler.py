from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.delete_sprint.command import DeleteSprint
from acli_py.application.ports import Sprints


@command_handler
def delete_sprint(request: DeleteSprint, sprints: Sprints) -> Changed:
    """Delete the sprint, keeping its name, state and goal in `before`."""
    old = sprints.sprint(request.sprint_id)
    sprints.delete(request.sprint_id)
    return Changed(
        request.item,
        before={"sprint": old.id, "name": old.name, "state": old.state.value, "goal": old.goal},
    )
