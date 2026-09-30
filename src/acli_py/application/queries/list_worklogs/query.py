from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_worklogs.view import WorklogsView


@query
@dataclass(frozen=True)
class ListWorklogs(Query[WorklogsView]):
    """The work logged on issue `key`."""

    key: str
