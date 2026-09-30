from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_watchers.view import WatchersView


@query
@dataclass(frozen=True)
class ListWatchers(Query[WatchersView]):
    """The people watching issue `key`."""

    key: str
