from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.delete_attachment.command import DeleteAttachment
from acli_py.application.ports import Attachments


@command_handler
def delete_attachment(request: DeleteAttachment, attachments: Attachments) -> Changed:
    """Delete the attachment, keeping its name and size in `before`.

    Jira doesn't say which issue an attachment is on, so `Changed` is keyed by the attachment.
    """
    found = attachments.attachment(request.attachment_id)
    attachments.delete(request.attachment_id)
    return Changed(
        f"attachment {request.attachment_id}",
        before={"attachment": request.attachment_id, "file": found.filename, "size": found.size},
    )
