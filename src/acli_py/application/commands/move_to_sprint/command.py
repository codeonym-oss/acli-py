from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class MoveToSprint(Command[Changed]):
    """Move issue `key` into sprint `sprint_id`, or (None) back to the backlog."""

    key: str
    sprint_id: int | None

    def change(self) -> Change:
        """Return what this command changes: 'Move DEMO-1 into sprint 8'."""
        where = f"into sprint {self.sprint_id}" if self.sprint_id else "to the backlog"
        return Change("Move", (self.key.strip().upper(),), where)
