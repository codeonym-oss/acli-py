"""`ChangesView`: what the audit log keeps."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from acli_py.application.changes import AuditRecord


@dataclass(frozen=True)
class ChangesView:
    """Records, newest first; `undone` maps each reversed record's id to its undo's."""

    entries: tuple[AuditRecord, ...]
    undone: Mapping[str, str] = field(default_factory=dict)

    def to_json(self) -> list[dict[str, Any]]:
        """Return the records as JSON."""
        return [
            {
                "id": e.id,
                "at": e.at.isoformat(),
                "command": e.command,
                "keys": list(e.keys),
                "failed": dict(e.failed),
                "undoes": e.undoes,
                "undoneBy": self.undone.get(e.id),
            }
            for e in self.entries
        ]
