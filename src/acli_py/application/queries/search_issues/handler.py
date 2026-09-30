from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import IssueSearch
from acli_py.application.queries.issue_columns import columns, jira_fields
from acli_py.application.queries.search_issues.query import SearchIssues
from acli_py.application.queries.search_issues.view import IssuesView


@query_handler
def search_issues(request: SearchIssues, search: IssueSearch) -> IssuesView:
    """Fetch the issues, with the fields their columns need."""
    shown = columns(request.fields)
    issues, token = search.search(
        request.jql, jira_fields(shown) or ("summary",), limit=request.limit, token=request.token
    )
    return IssuesView(request.jql, tuple(issues), shown, token)
