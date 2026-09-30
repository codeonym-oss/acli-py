from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Attachments
from acli_py.application.queries.list_attachments.query import ListAttachments
from acli_py.application.queries.list_attachments.view import AttachmentsView


@query_handler
def list_attachments(request: ListAttachments, attachments: Attachments) -> AttachmentsView:
    """Read the attachments."""
    key = request.key.strip().upper()
    return AttachmentsView(key, tuple(attachments.attachments(key)))
