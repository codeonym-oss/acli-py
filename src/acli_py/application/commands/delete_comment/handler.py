from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.delete_comment.command import DeleteComment
from acli_py.application.ports import Comments


@command_handler
def delete_comment(request: DeleteComment, comments: Comments) -> Changed:
    """Delete the comment, keeping its text and author in `before`."""
    key = request.key.strip().upper()
    old = comments.comment(key, request.comment_id)
    comments.delete(key, request.comment_id)
    author = old.author.account_id if old.author else ""
    return Changed(
        key, before={"comment": old.id or request.comment_id, "body": old.body, "author": author}
    )
