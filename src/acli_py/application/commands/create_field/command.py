from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed
from acli_py.domain.fields import custom_field_type


@command
@dataclass(frozen=True)
class CreateField(Command[Changed]):
    """Create custom field `name` of `type` (a name in `FIELD_TYPES`, or a full type key).

    `searcher` is how JQL searches it (default: the one that fits the type).
    """

    name: str
    type: str
    description: str | None = None
    searcher: str | None = None

    def __post_init__(self) -> None:
        """Refuse a type that isn't one."""
        custom_field_type(self.type, self.searcher)

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'field "…"'."""
        return f'field "{self.name}"'

    def change(self) -> Change:
        """Return what this command changes: 'Create field "Risk"'."""
        return Change("Create", (self.name,), subject=self.item, adds=True, noun="field")
