"""`WatchersView`: who watches an issue."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import user_json
from acli_py.domain.issue import User


@dataclass(frozen=True)
class WatchersView:
    """The people watching issue `key`."""

    key: str
    watchers: tuple[User, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return each watcher, and whether their account is active."""
        return [{**(user_json(u) or {}), "active": u.active} for u in self.watchers]
