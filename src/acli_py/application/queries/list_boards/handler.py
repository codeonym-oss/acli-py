from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Boards
from acli_py.application.queries.list_boards.query import ListBoards
from acli_py.application.queries.list_boards.view import BoardsView


@query_handler
def list_boards(request: ListBoards, boards: Boards) -> BoardsView:
    """Read the boards."""
    found = boards.boards(
        name=request.name,
        type=request.type,
        project=request.project.strip().upper() if request.project else None,
        filter_id=request.filter_id,
        order=request.order,
        private=request.private,
        limit=request.limit,
    )
    return BoardsView(tuple(found))
