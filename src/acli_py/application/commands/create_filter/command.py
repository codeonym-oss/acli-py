from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class CreateFilter(Command[Changed]):
    """Save `jql` as filter `name`, starred unless not `favourite`.

    `shares` are Jira's share permissions (None: Jira's default, private).
    """

    name: str
    jql: str
    description: str | None = None
    favourite: bool = True
    shares: tuple[Mapping[str, Any], ...] | None = None

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'filter "…"'."""
        return f'filter "{self.name}"'

    def change(self) -> Change:
        """Return what this command changes: 'Create filter "Bugs"'."""
        return Change("Create", (self.name,), subject=self.item, adds=True, noun="filter")
