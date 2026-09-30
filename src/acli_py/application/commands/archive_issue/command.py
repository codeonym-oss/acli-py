from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class ArchiveIssue(Command[Changed]):
    """Archive an issue, or (`archive` False) restore it."""

    key: str
    archive: bool = True

    def change(self) -> Change:
        """Return what this command changes: 'Archive DEMO-1', 'Unarchive DEMO-1'."""
        return Change("Archive" if self.archive else "Unarchive", (self.key.strip().upper(),))

    def previews(self) -> str | None:
        """Return the field the preview shows (none when restoring: search can't see those)."""
        return "status" if self.archive else None

    def after(self, now: Any) -> str:
        """Return what the issue will be."""
        return "archived" if self.archive else "restored"
