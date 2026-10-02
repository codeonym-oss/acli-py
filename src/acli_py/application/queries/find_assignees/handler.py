from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import People
from acli_py.application.queries.find_assignees.query import FindAssignees
from acli_py.application.queries.find_assignees.view import AssigneesView


@query_handler
def find_assignees(request: FindAssignees, people: People) -> AssigneesView:
    """Ask who can be assigned."""
    return AssigneesView(tuple(people.assignable(request.key.strip().upper(), request.text)))
