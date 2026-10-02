from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.get_board.view import BoardView


@query
@dataclass(frozen=True)
class GetBoard(Query[BoardView]):
    """Board `board_id`, its filter, columns and estimation."""

    board_id: int
