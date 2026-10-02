from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed

FIELDS = ("name", "description", "searcher")


@command
@dataclass(frozen=True)
class UpdateField(Command[Changed]):
    """Change what is given of custom field `field_id` (None: leave it)."""

    field_id: str
    name: str | None = None
    description: str | None = None
    searcher: str | None = None

    def __post_init__(self) -> None:
        """Refuse a change that changes nothing."""
        if all(getattr(self, f) is None for f in FIELDS):
            raise ValueError("Nothing to change. See acli-py field update --help.")

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'field customfield_10016'."""
        return f"field {self.field_id.strip()}"

    def change(self) -> Change:
        """Return what this command changes: 'Update field customfield_10016'."""
        return Change("Update", (self.field_id.strip(),), subject=self.item, noun="field")
