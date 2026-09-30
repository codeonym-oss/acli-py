from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed
from acli_py.domain.issue import Audience


@command
@dataclass(frozen=True)
class EditComment(Command[Changed]):
    """Replace comment `comment_id` on issue `key` with `body` (Markdown, or ADF JSON).

    `notify` emails the issue's watchers about the edit.
    """

    key: str
    comment_id: str
    body: str
    audience: Audience | None = None
    notify: bool = False

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'DEMO-1 comment 10001'."""
        return f"{self.key.strip().upper()} comment {self.comment_id}"

    def change(self) -> Change:
        """Return what this command changes: 'Edit comment 10001 on DEMO-1'."""
        subject = f"comment {self.comment_id} on {self.key.strip().upper()}"
        return Change("Edit", (self.comment_id,), subject=subject, noun="comment")
