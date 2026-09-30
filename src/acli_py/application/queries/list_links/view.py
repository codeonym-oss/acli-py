"""`LinksView`: an issue's links, one flat row each."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.domain.issue import Link


@dataclass(frozen=True)
class LinksView:
    """The links on issue `key`."""

    key: str
    links: tuple[Link, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return a row per link: its id, how it reads, and the other issue."""
        return [
            {
                "id": link.id,
                "type": link.type,
                "direction": link.direction.value,
                "phrase": link.phrase,
                "key": link.issue.key,
                "summary": link.issue.summary,
                "status": link.issue.status.name if link.issue.status else None,
            }
            for link in self.links
        ]
