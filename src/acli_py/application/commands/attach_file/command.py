from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class AttachFile(Command[Changed]):
    """Attach the file at `path` to issue `key`. One file doesn't ask first; several ask once."""

    key: str
    path: Path

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'DEMO-1 report.txt'."""
        return f"{self.key.strip().upper()} {self.path.name}"

    def change(self) -> Change:
        """Return what this command changes: 'Attach report.txt to DEMO-1'."""
        key = self.key.strip().upper()
        return Change(
            "Attach", (self.item,), subject=f"{self.path.name} to {key}", noun="file", adds=True
        )
