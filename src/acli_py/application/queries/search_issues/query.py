from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.search_issues.view import IssuesView


@query
@dataclass(frozen=True)
class SearchIssues(Query[IssuesView]):
    """Up to `limit` issues matching `jql` (None: all), from the page `token` names on.

    `fields` are the columns to show (see `issue_columns`); none shows the defaults.
    """

    jql: str
    limit: int | None = 50
    fields: tuple[str, ...] = ()
    token: str | None = None
