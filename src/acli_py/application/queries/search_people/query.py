from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.search_people.view import PeopleView


@query
@dataclass(frozen=True)
class SearchPeople(Query[PeopleView]):
    """Up to `limit` people whose name or email contain `text`."""

    text: str
    limit: int = 50
