"""`HistoryView`: an issue's changes, one row per field changed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from acli_py.application.queries.shapes import iso, user_json

if TYPE_CHECKING:
    from datetime import datetime

    from acli_py.domain.history import FieldChange
    from acli_py.domain.issue import User


@dataclass(frozen=True)
class HistoryRow:
    """One field changed, in the save (`entry`) that changed it."""

    entry: str
    at: datetime | None
    author: User | None
    change: FieldChange


@dataclass(frozen=True)
class HistoryView:
    """The changes to issue `key`."""

    key: str
    rows: tuple[HistoryRow, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return each change as JSON: `{id, at, author, field, fieldId, from, to}`."""
        return [
            {"id": r.entry, "at": iso(r.at), "author": user_json(r.author),
             "field": r.change.field, "fieldId": r.change.field_id or None,
             "from": r.change.before or None, "to": r.change.after or None}
            for r in self.rows
        ]  # fmt: skip
