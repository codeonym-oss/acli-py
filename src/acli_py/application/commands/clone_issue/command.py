from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class CloneIssue(Command[Changed]):
    """Copy an issue into `project` (default: its own), putting `prefix` before its summary.

    The copy is linked to the original when `link`: 'clones' on the same site, a web link back
    on another. Copying one issue doesn't ask first; copying several asks once.
    """

    key: str
    project: str = ""
    prefix: str = ""
    link: bool = True

    def change(self) -> Change:
        """Return what this command changes: 'Clone DEMO-1 into OPS'."""
        where = f"into {self.project.strip().upper()}" if self.project else ""
        return Change("Clone", (self.key.strip().upper(),), where, adds=True)
