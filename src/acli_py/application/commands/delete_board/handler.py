from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.delete_board.command import DeleteBoard
from acli_py.application.ports import Boards


@command_handler
def delete_board(request: DeleteBoard, boards: Boards) -> Changed:
    """Delete the board, keeping its name and filter in `before`."""
    old = boards.board(request.board_id)
    boards.delete(request.board_id)
    return Changed(
        request.item,
        before={"board": request.board_id, "name": old.board.name, "filter": old.filter_id},
    )
