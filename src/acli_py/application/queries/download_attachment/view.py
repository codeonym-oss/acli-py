"""`SavedFile`: an attachment saved to disk."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SavedFile:
    """Attachment `attachment_id`, saved at `path`: `size` bytes."""

    attachment_id: str
    path: Path
    size: int

    def to_json(self) -> dict[str, Any]:
        """Return where it went, as JSON."""
        return {"id": self.attachment_id, "path": str(self.path), "size": self.size}
