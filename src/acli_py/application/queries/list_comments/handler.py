from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Comments
from acli_py.application.queries.list_comments.query import ListComments
from acli_py.application.queries.list_comments.view import CommentsView


@query_handler
def list_comments(request: ListComments, comments: Comments) -> CommentsView:
    """Read the comments."""
    key = request.key.strip().upper()
    found = comments.comments(key, newest_first=request.newest_first, limit=request.limit)
    return CommentsView(key, tuple(found))
