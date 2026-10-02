from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed
from acli_py.domain.projects import ProjectSpec


@command
@dataclass(frozen=True)
class UpdateProject(Command[Changed]):
    """Change what `spec` gives of project `key` (a new `spec.key` renames it)."""

    key: str
    spec: ProjectSpec

    def __post_init__(self) -> None:
        """Refuse a change that changes nothing."""
        if self.spec.empty:
            raise ValueError("Nothing to change. See acli-py project update --help.")

    def change(self) -> Change:
        """Return what this command changes: 'Update project DEMO'."""
        key = self.key.strip().upper()
        return Change("Update", (key,), subject=f"project {key}", noun="project")
