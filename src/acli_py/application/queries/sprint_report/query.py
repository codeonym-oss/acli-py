from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.sprint_report.view import SprintReportView


@query
@dataclass(frozen=True)
class SprintReport(Query[SprintReportView]):
    """The progress of sprint `sprint_id`, or of the active sprint on board `board_id`."""

    sprint_id: int | None = None
    board_id: int | None = None

    def __post_init__(self) -> None:
        """Refuse a report on nothing."""
        if self.sprint_id is None and self.board_id is None:
            raise ValueError("Say which sprint, or which board's active sprint.")
