from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class RestoreField(Command[Changed]):
    """Restore custom field `field_id` from the trash."""

    field_id: str

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'field customfield_10016'."""
        return f"field {self.field_id.strip()}"

    def change(self) -> Change:
        """Return what this command changes: 'Restore field customfield_10030'."""
        return Change("Restore", (self.field_id.strip(),), subject=self.item, noun="field")
