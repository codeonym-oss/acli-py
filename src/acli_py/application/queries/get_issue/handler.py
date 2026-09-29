from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import IssueReader
from acli_py.application.queries.get_issue.query import GetIssue
from acli_py.application.queries.get_issue.view import IssueView


@query_handler
def get_issue(request: GetIssue, issues: IssueReader) -> IssueView:
    """Read the issue and wrap it in its view."""
    issue = issues.get_issue(request.key.strip().upper(), request.fields)
    return IssueView(issue, issues.browse_url(issue.key))
