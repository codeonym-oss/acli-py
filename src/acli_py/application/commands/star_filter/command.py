from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class StarFilter(Command[Changed]):
    """Star filter `filter_id`, or (not `star`) unstar it."""

    filter_id: str
    star: bool = True

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'filter 10100'."""
        return f"filter {self.filter_id.strip()}"

    def change(self) -> Change:
        """Return what this command changes: 'Star filter 10100'."""
        verb = "Star" if self.star else "Unstar"
        return Change(verb, (self.filter_id.strip(),), subject=self.item, noun="filter")
