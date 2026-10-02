from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed

BOARD_TYPES = ("scrum", "kanban")


@command
@dataclass(frozen=True)
class CreateBoard(Command[Changed]):
    """Create a `type` board named `name`, fed by filter `filter_id`.

    It goes in `project`, else it is the user's own board.
    """

    name: str
    filter_id: int
    type: str = "kanban"
    project: str | None = None

    def __post_init__(self) -> None:
        """Refuse a type Jira can't create."""
        if self.type not in BOARD_TYPES:
            raise ValueError("--type is scrum or kanban.")

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'board "…"'."""
        return f'board "{self.name}"'

    def change(self) -> Change:
        """Return what this command changes: 'Create board "Ops flow"'."""
        return Change("Create", (self.name,), subject=self.item, adds=True, noun="board")
