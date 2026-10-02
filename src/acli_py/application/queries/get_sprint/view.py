"""`SprintView`: one sprint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import sprint_json
from acli_py.domain.agile import Sprint


@dataclass(frozen=True)
class SprintView:
    """A sprint."""

    sprint: Sprint

    def to_json(self) -> dict[str, Any]:
        """Return the sprint as JSON."""
        return sprint_json(self.sprint)
