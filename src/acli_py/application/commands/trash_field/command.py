from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class TrashField(Command[Changed]):
    """Move custom field `field_id` to the trash."""

    field_id: str

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'field customfield_10016'."""
        return f"field {self.field_id.strip()}"

    def change(self) -> Change:
        """Return what this command changes: 'Move field customfield_10030 to the trash'."""
        return Change(
            "Move", (self.field_id.strip(),), "to the trash", subject=self.item, noun="field"
        )
