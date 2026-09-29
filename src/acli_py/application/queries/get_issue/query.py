from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.get_issue.view import IssueView


@query
@dataclass(frozen=True)
class GetIssue(Query[IssueView]):
    """An issue with everything a detail view shows.

    `fields` asks for more fields by id (custom fields, mostly); '*all' asks for every one.
    """

    key: str
    fields: tuple[str, ...] = ()
