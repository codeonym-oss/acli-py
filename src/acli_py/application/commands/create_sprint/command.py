from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class CreateSprint(Command[Changed]):
    """Create sprint `name` on board `board_id`, from `start` to `end`, aiming at `goal`."""

    board_id: int
    name: str
    start: datetime | None = None
    end: datetime | None = None
    goal: str | None = None

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'sprint "…"'."""
        return f'sprint "{self.name}"'

    def change(self) -> Change:
        """Return what this command changes: 'Create sprint "Sprint 9" on board 1'."""
        return Change(
            "Create",
            (self.name,),
            f"on board {self.board_id}",
            subject=self.item,
            adds=True,
            noun="sprint",
        )
