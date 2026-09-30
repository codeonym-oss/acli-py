from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Watchers
from acli_py.application.queries.list_watchers.query import ListWatchers
from acli_py.application.queries.list_watchers.view import WatchersView


@query_handler
def list_watchers(request: ListWatchers, watchers: Watchers) -> WatchersView:
    """Read the watchers."""
    key = request.key.strip().upper()
    return WatchersView(key, tuple(watchers.watchers(key)))
