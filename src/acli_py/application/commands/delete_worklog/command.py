from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class DeleteWorklog(Command[Changed]):
    """Delete worklog `worklog_id` from issue `key`, for good."""

    key: str
    worklog_id: str

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'DEMO-1 worklog 10001'."""
        return f"{self.key.strip().upper()} worklog {self.worklog_id}"

    def change(self) -> Change:
        """Return what this command changes: 'Delete worklog 10001 on DEMO-1'."""
        subject = f"worklog {self.worklog_id} on {self.key.strip().upper()}"
        return Change(
            "Delete", (self.worklog_id,), subject=subject, noun="worklog", destructive=True
        )
