from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import IssueSearch
from acli_py.application.queries.issue_columns import columns, jira_fields
from acli_py.application.queries.search_issues.view import IssuesView
from acli_py.application.queries.standup.query import Standup
from acli_py.application.queries.standup.view import StandupView
from acli_py.domain.helpers import last_working_day

DEFAULT_COLUMNS = ("key", "status", "priority", "summary")
NEXT = "assignee = currentUser() AND statusCategory != Done ORDER BY priority DESC, rank ASC"


@query_handler
def standup(request: Standup, search: IssueSearch) -> StandupView:
    """Search what the user changed since then, and what they have open."""
    since = request.since or last_working_day(request.today)
    shown = columns(request.fields or DEFAULT_COLUMNS)
    wanted = jira_fields(shown)
    changed_jql = (
        f'issuekey in updatedBy(currentUser(), "{since.isoformat()}") ORDER BY updated DESC'
    )
    changed, _ = search.search(changed_jql, wanted, limit=request.limit)
    upcoming, _ = search.search(NEXT, wanted, limit=request.limit)
    done = {i.key for i in changed}
    return StandupView(
        since,
        IssuesView(changed_jql, tuple(changed), shown),
        IssuesView(NEXT, tuple(i for i in upcoming if i.key not in done), shown),
    )
