from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class WatchIssue(Command[Changed]):
    """Make someone watch an issue, or (`watch` False) stop.

    `name` is how the person reads in questions; empty means it is the user themselves.
    """

    key: str
    account_id: str
    watch: bool = True
    name: str = ""

    def change(self) -> Change:
        """Return what this command changes: 'Watch DEMO-1', 'Make Bob stop watching DEMO-1'."""
        key = self.key.strip().upper()
        verb = "Watch" if self.watch else "Stop watching"
        if self.name:
            verb = f"Make {self.name} {verb.lower()}"
        return Change(verb, (key,))
