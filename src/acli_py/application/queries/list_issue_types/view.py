"""`IssueTypesView`: issue types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.domain.meta import IssueTypeInfo


@dataclass(frozen=True)
class IssueTypesView:
    """Issue types, in the site's order."""

    types: tuple[IssueTypeInfo, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return the types as JSON."""
        return [
            {
                "id": t.id,
                "name": t.name,
                "subtask": t.subtask,
                "hierarchyLevel": t.level,
                "description": t.description or None,
            }
            for t in self.types
        ]
