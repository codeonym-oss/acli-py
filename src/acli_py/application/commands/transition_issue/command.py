from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class TransitionIssue(Command[Changed]):
    """Move an issue to another status, optionally setting fields and adding a comment.

    `to` names the target status, or the transition's name or id. `fields` are set on the way
    (the resolution, mostly), in the shape Jira takes them.
    """

    key: str
    to: str
    comment: str = ""
    fields: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def change(self) -> Change:
        """Return what this command changes."""
        return Change("Move", (self.key.strip().upper(),), f"to {self.to.strip()}")

    def previews(self) -> str:
        """Return the field this command sets (for a bulk run's preview)."""
        return "status"

    def after(self, now: Any) -> str:
        """Return the status the issue will be in."""
        return self.to.strip()
