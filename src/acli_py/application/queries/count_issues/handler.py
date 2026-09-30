from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import IssueSearch
from acli_py.application.queries.count_issues.query import CountIssues


@query_handler
def count_issues(request: CountIssues, search: IssueSearch) -> int:
    """Return Jira's estimate."""
    return search.count(request.jql)
