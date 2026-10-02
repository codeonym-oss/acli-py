from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Boards
from acli_py.application.queries.get_board.query import GetBoard
from acli_py.application.queries.get_board.view import BoardView


@query_handler
def get_board(request: GetBoard, boards: Boards) -> BoardView:
    """Read the board."""
    return BoardView(boards.board(request.board_id))
