"""`WorklogsView`: the work logged on an issue."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import worklog_json
from acli_py.domain.issue import Worklog


@dataclass(frozen=True)
class WorklogsView:
    """The worklogs on issue `key`."""

    key: str
    worklogs: tuple[Worklog, ...]

    @property
    def seconds(self) -> int:
        """Return the time logged in all, in seconds."""
        return sum(w.seconds for w in self.worklogs)

    def to_json(self) -> list[dict[str, Any]]:
        """Return the worklogs as JSON."""
        return [worklog_json(w) for w in self.worklogs]
