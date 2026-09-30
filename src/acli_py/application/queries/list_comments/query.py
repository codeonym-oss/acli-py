from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_comments.view import CommentsView


@query
@dataclass(frozen=True)
class ListComments(Query[CommentsView]):
    """Issue `key`'s comments, oldest first unless `newest_first`; at most `limit` (None: all)."""

    key: str
    newest_first: bool = False
    limit: int | None = 50
