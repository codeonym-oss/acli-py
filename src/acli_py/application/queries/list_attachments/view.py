"""`AttachmentsView`: an issue's attachments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import attachment_json
from acli_py.domain.issue import Attachment


@dataclass(frozen=True)
class AttachmentsView:
    """The files attached to issue `key`."""

    key: str
    attachments: tuple[Attachment, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return the attachments as JSON."""
        return [attachment_json(a) for a in self.attachments]
