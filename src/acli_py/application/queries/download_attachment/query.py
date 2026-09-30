from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from mediary.cqrs import Query, query

from acli_py.application.queries.download_attachment.view import SavedFile


@query
@dataclass(frozen=True)
class DownloadAttachment(Query[SavedFile]):
    """Save attachment `attachment_id` into the existing folder `folder`, under its own name."""

    attachment_id: str
    folder: Path

    cacheable: ClassVar[bool] = False  # it writes a file: run it every time
