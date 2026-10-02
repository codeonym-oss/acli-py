"""`ProjectView`: one project in detail."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import project_json
from acli_py.domain.projects import Project


@dataclass(frozen=True)
class ProjectView:
    """A project."""

    project: Project

    def to_json(self) -> dict[str, Any]:
        """Return the project as JSON."""
        return project_json(self.project)
