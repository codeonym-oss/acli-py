from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Sprints
from acli_py.application.queries.sprint_report.query import SprintReport
from acli_py.application.queries.sprint_report.view import SprintReportView
from acli_py.domain.agile import SprintState

FIELDS = ("summary", "status", "assignee")


@query_handler
def sprint_report(request: SprintReport, sprints: Sprints) -> SprintReportView:
    """Find the sprint, then read all its issues."""
    if request.sprint_id is not None:
        sprint = sprints.sprint(request.sprint_id)
    else:
        assert request.board_id is not None  # SprintReport refuses neither
        active = sprints.sprints(request.board_id, (SprintState.ACTIVE,), limit=1)
        if not active:
            raise ValueError(f"Board {request.board_id} has no active sprint.")
        sprint = active[0]
    return SprintReportView(sprint, tuple(sprints.issues(sprint.id, None, FIELDS, limit=None)))
