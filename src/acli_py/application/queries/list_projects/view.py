"""`ProjectsView`: a list of projects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import project_json
from acli_py.domain.projects import Project


@dataclass(frozen=True)
class ProjectsView:
    """Projects, in the order found."""

    projects: tuple[Project, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return the projects as JSON."""
        return [project_json(p) for p in self.projects]
