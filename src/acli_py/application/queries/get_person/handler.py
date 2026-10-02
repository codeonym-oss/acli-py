from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import People
from acli_py.application.queries.get_person.query import GetPerson
from acli_py.application.queries.search_people.view import PeopleView


@query_handler
def get_person(request: GetPerson, people: People) -> PeopleView:
    """Read the profile."""
    return PeopleView((people.profile(request.who),))
