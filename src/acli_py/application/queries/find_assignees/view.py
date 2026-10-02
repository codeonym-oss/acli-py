"""`AssigneesView`: people who can be assigned an issue."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import user_json
from acli_py.domain.issue import User


@dataclass(frozen=True)
class AssigneesView:
    """People, as the site found them."""

    people: tuple[User, ...]

    def to_json(self) -> list[dict[str, Any] | None]:
        """Return the people as JSON."""
        return [user_json(p) for p in self.people]
