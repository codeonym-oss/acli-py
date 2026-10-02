from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_boards.view import BoardsView


@query
@dataclass(frozen=True)
class ListBoards(Query[BoardsView]):
    """Up to `limit` boards (None: all) matching what is given.

    `order` is 'name', or '-name' for Z to A; `private` also lists private boards.
    """

    name: str | None = None
    type: str | None = None
    project: str | None = None
    filter_id: str | None = None
    order: str | None = None
    private: bool = False
    limit: int | None = 50
