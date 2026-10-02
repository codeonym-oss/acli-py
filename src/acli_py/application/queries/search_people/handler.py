from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import People
from acli_py.application.queries.search_people.query import SearchPeople
from acli_py.application.queries.search_people.view import PeopleView


@query_handler
def search_people(request: SearchPeople, people: People) -> PeopleView:
    """Search."""
    return PeopleView(tuple(people.search(request.text, limit=request.limit)))
