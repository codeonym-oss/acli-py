from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed
from acli_py.domain.projects import ProjectSpec


@command
@dataclass(frozen=True)
class CreateProject(Command[Changed]):
    """Create the project `spec` describes, led by `spec.lead` (default: the user).

    With `like`, it shares that company-managed project's type, category and schemes
    instead of starting from a template. Creating one project doesn't ask first.
    """

    spec: ProjectSpec
    like: str | None = None

    def __post_init__(self) -> None:
        """Refuse a project without a key and a name."""
        if not self.spec.key or not self.spec.name:
            raise ValueError("A new project needs --key and --name.")

    @property
    def key(self) -> str:
        """Return the new project's key."""
        return str(self.spec.key).upper()

    def change(self) -> Change:
        """Return what this command changes: 'Create project OPS'."""
        return Change(
            "Create", (self.key,), subject=f"project {self.key}", adds=True, noun="project"
        )
