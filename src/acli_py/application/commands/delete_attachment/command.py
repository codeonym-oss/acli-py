from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class DeleteAttachment(Command[Changed]):
    """Delete attachment `attachment_id` (see `issue attachment list`), for good."""

    attachment_id: str

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'attachment 10001'."""
        return f"attachment {self.attachment_id}"

    def change(self) -> Change:
        """Return what this command changes: 'Delete attachment 10001'."""
        return Change(
            "Delete", (self.attachment_id,), subject=self.item, noun="attachment", destructive=True
        )
