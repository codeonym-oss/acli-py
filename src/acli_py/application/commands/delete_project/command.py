from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class DeleteProject(Command[Changed]):
    """Move project `key` to the trash (restorable for 60 days), or (`permanent`) delete it.

    Deleting it for good takes its issues with it, so that can't be undone.
    """

    key: str
    permanent: bool = False

    def change(self) -> Change:
        """Return what this command changes: 'Move project DEMO to the trash'."""
        key = self.key.strip().upper()
        if self.permanent:
            return Change(
                "Permanently delete",
                (key,),
                "and all its issues",
                subject=f"project {key}",
                noun="project",
                destructive=True,
            )
        return Change("Move", (key,), "to the trash", subject=f"project {key}", noun="project")
