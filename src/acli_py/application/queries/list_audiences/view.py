"""`AudiencesView`: who a comment can be kept to."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.domain.issue import Audience


@dataclass(frozen=True)
class AudiencesView:
    """Roles or groups."""

    audiences: tuple[Audience, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return each one's kind ('role', 'group') and name."""
        return [{"type": a.kind, "name": a.name} for a in self.audiences]
