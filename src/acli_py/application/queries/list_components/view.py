"""`ComponentsView`: a project's components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import component_json
from acli_py.domain.projects import Component


@dataclass(frozen=True)
class ComponentsView:
    """The components of project `key`."""

    key: str
    components: tuple[Component, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return the components as JSON."""
        return [component_json(c) for c in self.components]
