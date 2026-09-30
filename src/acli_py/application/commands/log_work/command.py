from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed
from acli_py.domain.issue import is_duration


@command
@dataclass(frozen=True)
class LogWork(Command[Changed]):
    """Log `spent` ('1h 30m', '2d') on issue `key`, started at `started` (default: now).

    `comment` (Markdown) says what was done; `remaining` sets the remaining estimate (else
    Jira lowers it by `spent`). Logging on one issue doesn't ask first; on several, it asks once.
    """

    key: str
    spent: str
    comment: str = ""
    started: datetime | None = None
    remaining: str = ""

    def __post_init__(self) -> None:
        """Refuse what isn't a duration."""
        if not is_duration(self.spent):
            raise ValueError(f"{self.spent!r} is not a duration like 1h 30m, 2d or 45m.")

    def change(self) -> Change:
        """Return what this command changes: 'Log 1h 30m on DEMO-1'."""
        return Change(f"Log {self.spent.strip()} on", (self.key.strip().upper(),), adds=True)
