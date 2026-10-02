from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import People
from acli_py.application.queries.find_person.query import (
    DEFAULT,
    NOBODY,
    PROJECT_DEFAULT,
    FindPerson,
)


@query_handler
def find_person(request: FindPerson, people: People) -> str | None:
    """Return the account id."""
    word = request.who.strip().lower()
    if request.assignee and word in NOBODY:
        return None
    if request.assignee and word == DEFAULT:
        return PROJECT_DEFAULT
    return people.account_id(request.who)
