from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import SiteLists
from acli_py.application.queries.list_issue_types.query import ListIssueTypes
from acli_py.application.queries.list_issue_types.view import IssueTypesView


@query_handler
def list_issue_types(request: ListIssueTypes, lists: SiteLists) -> IssueTypesView:
    """Read the issue types."""
    project = request.project.strip().upper() if request.project else None
    found = lists.issue_types(project)
    if request.creatable:
        found = [t for t in found if not t.subtask]
    return IssueTypesView(tuple(found))
