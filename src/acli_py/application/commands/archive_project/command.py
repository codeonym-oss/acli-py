from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class ArchiveProject(Command[Changed]):
    """Archive project `key`."""

    key: str

    def change(self) -> Change:
        """Return what this command changes: 'Archive project DEMO'."""
        key = self.key.strip().upper()
        return Change("Archive", (key,), subject=f"project {key}", noun="project")
