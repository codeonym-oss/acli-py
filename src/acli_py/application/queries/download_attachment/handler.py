from __future__ import annotations

from pathlib import Path

from mediary.cqrs import query_handler

from acli_py.application.ports import Attachments
from acli_py.application.queries.download_attachment.query import DownloadAttachment
from acli_py.application.queries.download_attachment.view import SavedFile


@query_handler
def download_attachment(request: DownloadAttachment, attachments: Attachments) -> SavedFile:
    """Save the file under its own name (only the name: never a path Jira sends)."""
    found = attachments.attachment(request.attachment_id)
    dest = request.folder / (Path(found.filename).name or request.attachment_id)
    return SavedFile(request.attachment_id, dest, attachments.download(request.attachment_id, dest))
