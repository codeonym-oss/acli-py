from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed
from acli_py.domain.agile import SPRINT_WEEKS


@command
@dataclass(frozen=True)
class StartSprint(Command[Changed]):
    """Start sprint `sprint_id`, from `start` to `end`, else for `weeks` from now.

    Dates the sprint already has are kept when none are given.
    """

    sprint_id: int
    start: datetime | None = None
    end: datetime | None = None
    weeks: int = SPRINT_WEEKS
    goal: str | None = None

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'sprint 8'."""
        return f"sprint {self.sprint_id}"

    def change(self) -> Change:
        """Return what this command changes: 'Start sprint 8'."""
        return Change("Start", (str(self.sprint_id),), subject=self.item, noun="sprint")
