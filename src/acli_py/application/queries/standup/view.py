"""`StandupView`: what changed since the last working day, and what is next."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from acli_py.application.queries.search_issues.view import IssuesView


@dataclass(frozen=True)
class StandupView:
    """The issues changed since `since`, and the open ones not among them."""

    since: date
    changed: IssuesView
    next: IssuesView

    def to_json(self) -> dict[str, Any]:
        """Return both lists as JSON."""
        return {
            "since": self.since.isoformat(),
            "changed": self.changed.to_json(),
            "next": self.next.to_json(),
        }

    def rows(self) -> list[dict[str, Any]]:
        """Return one JSON object per issue, saying which list it is in (for JSON lines)."""
        return [
            {"list": name, **row}
            for name, view in (("changed", self.changed), ("next", self.next))
            for row in view.to_json()
        ]
