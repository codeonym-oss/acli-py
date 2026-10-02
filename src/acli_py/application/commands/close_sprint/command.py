from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class CloseSprint(Command[Changed]):
    """Close sprint `sprint_id`."""

    sprint_id: int

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'sprint 8'."""
        return f"sprint {self.sprint_id}"

    def change(self) -> Change:
        """Return what this command changes: 'Close sprint 7'."""
        return Change("Close", (str(self.sprint_id),), subject=self.item, noun="sprint")
