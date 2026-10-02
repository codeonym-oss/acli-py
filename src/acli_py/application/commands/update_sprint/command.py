from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed

FIELDS = ("name", "start", "end", "goal")


@command
@dataclass(frozen=True)
class UpdateSprint(Command[Changed]):
    """Change what is given of sprint `sprint_id` (None: leave it)."""

    sprint_id: int
    name: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    goal: str | None = None

    def __post_init__(self) -> None:
        """Refuse a change that changes nothing."""
        if all(getattr(self, f) is None for f in FIELDS):
            raise ValueError("Nothing to change. See acli-py sprint update --help.")

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'sprint 8'."""
        return f"sprint {self.sprint_id}"

    def change(self) -> Change:
        """Return what this command changes: 'Update sprint 8'."""
        return Change("Update", (str(self.sprint_id),), subject=self.item, noun="sprint")
