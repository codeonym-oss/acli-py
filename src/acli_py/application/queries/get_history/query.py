from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.get_history.view import HistoryView


@query
@dataclass(frozen=True)
class GetHistory(Query[HistoryView]):
    """Issue `key`'s changes, oldest first unless `newest_first`; only `field`'s when given."""

    key: str
    field: str = ""
    newest_first: bool = False
    limit: int | None = None
