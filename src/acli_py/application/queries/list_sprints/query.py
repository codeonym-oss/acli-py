from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_sprints.view import SprintsView
from acli_py.domain.agile import SprintState


@query
@dataclass(frozen=True)
class ListSprints(Query[SprintsView]):
    """Up to `limit` (None: all) of board `board_id`'s sprints in `states` (none: all)."""

    board_id: int
    states: tuple[SprintState, ...] = ()
    limit: int | None = 50
