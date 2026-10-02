from __future__ import annotations

from datetime import UTC, datetime

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.start_sprint.command import StartSprint
from acli_py.application.ports import Sprints
from acli_py.domain.agile import SprintState


@command_handler
def start_sprint(request: StartSprint, sprints: Sprints) -> Changed:
    """Start the sprint; `after` says when it runs."""
    sprint = sprints.sprint(request.sprint_id)
    start, end = sprint.schedule(datetime.now(UTC), request.start, request.end, request.weeks)
    sprints.update(
        request.sprint_id, state=SprintState.ACTIVE, start=start, end=end, goal=request.goal
    )
    return Changed(
        request.item,
        before={"state": sprint.state.value},
        after={"state": SprintState.ACTIVE.value, "start": start, "end": end},
    )
