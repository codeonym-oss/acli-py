from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Boards
from acli_py.application.queries.list_board_projects.query import ListBoardProjects
from acli_py.application.queries.list_projects.view import ProjectsView


@query_handler
def list_board_projects(request: ListBoardProjects, boards: Boards) -> ProjectsView:
    """Read the board's projects."""
    return ProjectsView(tuple(boards.projects(request.board_id, limit=request.limit)))
