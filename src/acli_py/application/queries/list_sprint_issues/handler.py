from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Sprints
from acli_py.application.queries.issue_columns import columns, jira_fields
from acli_py.application.queries.list_sprint_issues.query import ListSprintIssues
from acli_py.application.queries.search_issues.view import IssuesView


@query_handler
def list_sprint_issues(request: ListSprintIssues, sprints: Sprints) -> IssuesView:
    """Fetch the sprint's issues, with the fields their columns need."""
    shown = columns(request.fields)
    found = sprints.issues(request.sprint_id, request.jql, jira_fields(shown), limit=request.limit)
    return IssuesView(request.jql or "", tuple(found), shown)
