"""`GitNames`: what an issue is called in git."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class GitNames:
    """A branch and a commit message for issue `key`."""

    key: str
    branch: str
    commit: str

    def to_json(self) -> dict[str, Any]:
        """Return the names as JSON."""
        return asdict(self)
