from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class RestoreProject(Command[Changed]):
    """Restore project `key` from the trash or the archive."""

    key: str

    def change(self) -> Change:
        """Return what this command changes: 'Restore project DEMO'."""
        key = self.key.strip().upper()
        return Change("Restore", (key,), subject=f"project {key}", noun="project")
