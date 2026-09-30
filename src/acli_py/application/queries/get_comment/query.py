from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.domain.issue import Comment


@query
@dataclass(frozen=True)
class GetComment(Query[Comment]):
    """Comment `comment_id` on issue `key`, its body as Markdown."""

    key: str
    comment_id: str
