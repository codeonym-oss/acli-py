"""`NamedView`: a plain list of the site's (priorities, resolutions)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.domain.meta import Named


@dataclass(frozen=True)
class NamedView:
    """Entries, in the site's order."""

    entries: tuple[Named, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return the entries as JSON."""
        return [
            {"id": e.id, "name": e.name, "description": e.description or None} for e in self.entries
        ]
