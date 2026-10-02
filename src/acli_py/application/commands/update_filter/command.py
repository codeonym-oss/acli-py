from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed

FIELDS = ("name", "jql", "description", "shares", "edit_shares")


@command
@dataclass(frozen=True)
class UpdateFilter(Command[Changed]):
    """Change what is given of filter `filter_id` (None: leave it)."""

    filter_id: str
    name: str | None = None
    jql: str | None = None
    description: str | None = None
    shares: tuple[Mapping[str, Any], ...] | None = None
    edit_shares: tuple[Mapping[str, Any], ...] | None = None

    def __post_init__(self) -> None:
        """Refuse a change that changes nothing."""
        if all(getattr(self, f) is None for f in FIELDS):
            raise ValueError("Nothing to change. See acli-py filter update --help.")

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'filter 10100'."""
        return f"filter {self.filter_id.strip()}"

    def change(self) -> Change:
        """Return what this command changes: 'Update filter 10100'."""
        return Change("Update", (self.filter_id.strip(),), subject=self.item, noun="filter")
