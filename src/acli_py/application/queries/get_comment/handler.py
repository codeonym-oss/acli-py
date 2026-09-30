from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Comments
from acli_py.application.queries.get_comment.query import GetComment
from acli_py.domain.issue import Comment


@query_handler
def get_comment(request: GetComment, comments: Comments) -> Comment:
    """Read the comment."""
    return comments.comment(request.key.strip().upper(), request.comment_id)
