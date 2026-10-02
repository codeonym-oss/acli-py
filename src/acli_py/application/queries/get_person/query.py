from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.search_people.view import PeopleView


@query
@dataclass(frozen=True)
class GetPerson(Query[PeopleView]):
    """The profile of the person `who` names: '@me', an email, a name or an account id."""

    who: str = "@me"
