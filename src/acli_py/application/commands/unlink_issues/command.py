from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class UnlinkIssues(Command[Changed]):
    """Remove link `link_id` (see `issue link list`)."""

    link_id: str

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'link 10001'."""
        return f"link {self.link_id}"

    def change(self) -> Change:
        """Return what this command changes: 'Delete link 10001'."""
        return Change("Delete", (self.link_id,), subject=self.item, noun="link", destructive=True)
