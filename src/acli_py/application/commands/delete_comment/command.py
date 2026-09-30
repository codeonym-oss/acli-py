from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class DeleteComment(Command[Changed]):
    """Delete comment `comment_id` from issue `key`, for good."""

    key: str
    comment_id: str

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'DEMO-1 comment 10001'."""
        return f"{self.key.strip().upper()} comment {self.comment_id}"

    def change(self) -> Change:
        """Return what this command changes: 'Delete comment 10001 on DEMO-1'."""
        subject = f"comment {self.comment_id} on {self.key.strip().upper()}"
        return Change(
            "Delete", (self.comment_id,), subject=subject, noun="comment", destructive=True
        )
