from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.edit_comment.command import EditComment
from acli_py.application.ports import Comments
from acli_py.domain import adf


@command_handler
def edit_comment(request: EditComment, comments: Comments) -> Changed:
    """Replace the comment's text, keeping the old text in `before`."""
    key = request.key.strip().upper()
    old = comments.comment(key, request.comment_id)
    body = adf.to_adf(request.body)
    comments.update(key, request.comment_id, body, request.audience, notify=request.notify)
    return Changed(
        key,
        before={"comment": request.comment_id, "body": old.body},
        after={"comment": request.comment_id, "body": adf.to_text(body).strip()},
    )
