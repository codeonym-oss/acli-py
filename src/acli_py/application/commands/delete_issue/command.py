from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class DeleteIssue(Command[Changed]):
    """Delete an issue for good, with its subtasks when `subtasks` (else Jira refuses)."""

    key: str
    subtasks: bool = False

    def change(self) -> Change:
        """Return what this command changes: 'Permanently delete DEMO-1'."""
        detail = "with their subtasks" if self.subtasks else ""
        return Change("Permanently delete", (self.key.strip().upper(),), detail, destructive=True)

    def previews(self) -> str:
        """Return the field the preview shows: the status the issue is leaving."""
        return "status"

    def after(self, now: Any) -> str:
        """Return what the issue will be."""
        return "deleted"
