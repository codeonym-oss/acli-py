from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.search_issues.view import IssuesView


@query
@dataclass(frozen=True)
class ListSprintIssues(Query[IssuesView]):
    """Up to `limit` issues (None: all) in sprint `sprint_id`, matching `jql`.

    `fields` are the columns to show (see `issue_columns`); none shows the defaults.
    """

    sprint_id: int
    jql: str | None = None
    limit: int | None = 50
    fields: tuple[str, ...] = ()
