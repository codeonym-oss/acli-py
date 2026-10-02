from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.create_board.command import CreateBoard
from acli_py.application.ports import Boards, People


@command_handler
def create_board(request: CreateBoard, boards: Boards, people: People) -> Changed:
    """Create the board; `after` names it."""
    project = request.project.strip().upper() if request.project else None
    owner = "" if project else people.account_id("@me")
    board_id = boards.create(request.name, request.type, request.filter_id, project, owner)
    return Changed(f"board {board_id}", after={"board": board_id, "name": request.name})
