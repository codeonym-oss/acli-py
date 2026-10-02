from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class DeleteFilter(Command[Changed]):
    """Delete filter `filter_id`, for good."""

    filter_id: str

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'filter 10100'."""
        return f"filter {self.filter_id.strip()}"

    def change(self) -> Change:
        """Return what this command changes: 'Delete filter 10100'."""
        return Change(
            "Delete", (self.filter_id.strip(),), subject=self.item, noun="filter", destructive=True
        )
