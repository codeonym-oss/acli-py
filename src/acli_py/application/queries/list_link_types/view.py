"""`LinkTypesView`: the site's link types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.domain.links import LinkType


@dataclass(frozen=True)
class LinkTypesView:
    """The kinds of link there are."""

    types: tuple[LinkType, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return each type: its id, name and phrases."""
        return [
            {"id": t.id, "name": t.name, "outward": t.outward, "inward": t.inward}
            for t in self.types
        ]
