from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.search_issues.view import IssuesView


@query
@dataclass(frozen=True)
class ListBacklog(Query[IssuesView]):
    """Up to `limit` issues (None: all) in board `board_id`'s backlog, matching `jql`.

    `fields` are the columns to show (see `issue_columns`); none shows the defaults.
    """

    board_id: int
    jql: str | None = None
    limit: int | None = 50
    fields: tuple[str, ...] = ()
