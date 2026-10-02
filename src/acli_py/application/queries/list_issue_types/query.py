from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_issue_types.view import IssueTypesView


@query
@dataclass(frozen=True)
class ListIssueTypes(Query[IssueTypesView]):
    """The issue types project `project` uses (None: the site's).

    `creatable` leaves out subtasks, which need a parent.
    """

    project: str | None = None
    creatable: bool = False
