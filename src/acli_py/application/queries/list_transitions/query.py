from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_transitions.view import TransitionsView


@query
@dataclass(frozen=True)
class ListTransitions(Query[TransitionsView]):
    """The transitions available on issue `key` now."""

    key: str
