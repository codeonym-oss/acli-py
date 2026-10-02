"""`SprintsView`: a list of sprints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import sprint_json
from acli_py.domain.agile import Sprint, SprintState


@dataclass(frozen=True)
class SprintsView:
    """Sprints, oldest first."""

    sprints: tuple[Sprint, ...]

    @property
    def active(self) -> Sprint | None:
        """Return the first active sprint, if any."""
        return next((s for s in self.sprints if s.state is SprintState.ACTIVE), None)

    def to_json(self) -> list[dict[str, Any]]:
        """Return the sprints as JSON."""
        return [sprint_json(s) for s in self.sprints]
