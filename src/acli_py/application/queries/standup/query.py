from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from mediary.cqrs import Query, query

from acli_py.application.queries.standup.view import StandupView


@query
@dataclass(frozen=True)
class Standup(Query[StandupView]):
    """What the user changed since `since`, and their open issues, most important first.

    `since` defaults to the last working day before `today`; `fields` are the columns.
    """

    today: date
    since: date | None = None
    fields: tuple[str, ...] = ()
    limit: int = 50
