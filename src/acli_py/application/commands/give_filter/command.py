from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class GiveFilter(Command[Changed]):
    """Make `to` ('@me', an email, a name, an account id) the owner of filter `filter_id`."""

    filter_id: str
    to: str

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'filter 10100'."""
        return f"filter {self.filter_id.strip()}"

    def change(self) -> Change:
        """Return what this command changes: 'Give filter 10100 to bob@example.com'."""
        return Change(
            "Give", (self.filter_id.strip(),), f"to {self.to}", subject=self.item, noun="filter"
        )
