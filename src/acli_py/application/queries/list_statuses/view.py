"""`StatusesView`: the site's statuses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.domain.meta import StatusInfo


@dataclass(frozen=True)
class StatusesView:
    """Statuses."""

    statuses: tuple[StatusInfo, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return the statuses as JSON."""
        return [
            {
                "id": s.id,
                "name": s.name,
                "category": s.category_name or None,
                "projectId": s.project_id or None,
            }
            for s in self.statuses
        ]
