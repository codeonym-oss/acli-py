from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Comments
from acli_py.application.queries.list_audiences.query import ListAudiences
from acli_py.application.queries.list_audiences.view import AudiencesView


@query_handler
def list_audiences(request: ListAudiences, comments: Comments) -> AudiencesView:
    """Read the roles or groups."""
    return AudiencesView(tuple(comments.audiences(request.project.strip().upper() or None)))
