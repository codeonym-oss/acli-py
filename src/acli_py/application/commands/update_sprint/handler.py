from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.update_sprint.command import FIELDS, UpdateSprint
from acli_py.application.ports import Sprints


@command_handler
def update_sprint(request: UpdateSprint, sprints: Sprints) -> Changed:
    """Change the sprint, keeping what the changed values were."""
    old = sprints.sprint(request.sprint_id)
    sprints.update(
        request.sprint_id,
        name=request.name,
        start=request.start,
        end=request.end,
        goal=request.goal,
    )
    given = [f for f in FIELDS if getattr(request, f) is not None]
    return Changed(
        request.item,
        before={f: getattr(old, f) for f in given},
        after={f: getattr(request, f) for f in given},
    )
