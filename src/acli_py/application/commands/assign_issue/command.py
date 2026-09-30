from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed

DEFAULT = "-1"  # Jira's account id for "the project's default assignee"


@command
@dataclass(frozen=True)
class AssignIssue(Command[Changed]):
    """Assign an issue: `account_id` None unassigns it, '-1' picks the project's default.

    `name` is how the person reads in questions and messages.
    """

    key: str
    account_id: str | None
    name: str = ""

    @property
    def who(self) -> str:
        """Return the assignee as a person reads it."""
        if self.account_id is None:
            return "nobody"
        if self.account_id == DEFAULT:
            return "the default assignee"
        return self.name or self.account_id

    def change(self) -> Change:
        """Return what this command changes: 'Assign DEMO-1 to Bob', 'Unassign DEMO-1'."""
        key = self.key.strip().upper()
        if self.account_id is None:
            return Change("Unassign", (key,))
        return Change("Assign", (key,), f"to {self.who}")

    def previews(self) -> str:
        """Return the field this command sets (for a bulk run's preview)."""
        return "assignee"

    def after(self, now: Any) -> str:
        """Return who the issue will be assigned to."""
        return "" if self.account_id is None else self.who
