"""An issue's history: who changed which fields, when, from what to what.

Jira keeps it as a changelog of entries; each entry is one save by one person, and changes
one or more fields. Values are the text Jira shows (`fromString`/`toString`), not ids.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from acli_py.domain.issue import User
from acli_py.domain.values import moment

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True)
class FieldChange:
    """One field's change: 'status: To Do → In Progress'."""

    field: str
    before: str = ""
    after: str = ""
    field_id: str = ""

    @classmethod
    def from_jira(cls, data: Any) -> FieldChange:
        """Return the change in one of a changelog entry's `items`."""
        data = data if isinstance(data, dict) else {}
        return cls(
            str(data.get("field") or data.get("fieldId") or ""),
            str(data.get("fromString") or data.get("from") or ""),
            str(data.get("toString") or data.get("to") or ""),
            str(data.get("fieldId") or ""),
        )

    def about(self, name: str) -> bool:
        """Return whether this changes the field called `name` (its name or id, any case)."""
        return name.strip().lower() in (self.field.lower(), self.field_id.lower())

    def __str__(self) -> str:
        """Return 'status: To Do → In Progress'."""
        return f"{self.field}: {self.before or '∅'} → {self.after or '∅'}"


@dataclass(frozen=True)
class HistoryEntry:
    """One save: who made it, when, and the fields it changed."""

    id: str
    author: User | None
    at: datetime | None
    changes: tuple[FieldChange, ...]

    @classmethod
    def from_jira(cls, data: Any) -> HistoryEntry:
        """Return the entry in `GET /issue/{key}/changelog`'s `values`."""
        data = data if isinstance(data, dict) else {}
        return cls(
            str(data.get("id") or ""),
            User.from_jira(data.get("author")),
            moment(data.get("created")),
            tuple(FieldChange.from_jira(item) for item in data.get("items") or ()),
        )
