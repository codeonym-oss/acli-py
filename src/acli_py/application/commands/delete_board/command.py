from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class DeleteBoard(Command[Changed]):
    """Delete board `board_id`, for good."""

    board_id: int

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'board 12'."""
        return f"board {self.board_id}"

    def change(self) -> Change:
        """Return what this command changes: 'Delete board 12'."""
        return Change(
            "Delete", (str(self.board_id),), subject=self.item, noun="board", destructive=True
        )
