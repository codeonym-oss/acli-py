"""`TransitionsView`: where an issue can go from here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.domain.workflow import Transition


@dataclass(frozen=True)
class TransitionsView:
    """The transitions of issue `key`."""

    key: str
    transitions: tuple[Transition, ...]

    @property
    def targets(self) -> set[str]:
        """Return the statuses the issue can move to."""
        return {t.target for t in self.transitions}

    def to_json(self) -> list[dict[str, Any]]:
        """Return the transitions as JSON."""
        return [
            {
                "id": t.id,
                "name": t.name,
                "to": t.target,
                "category": (t.to.category.label or None) if t.to else None,
            }
            for t in self.transitions
        ]
