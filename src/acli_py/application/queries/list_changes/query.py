from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from mediary.cqrs import Query, query

from acli_py.application.queries.list_changes.view import ChangesView


@query
@dataclass(frozen=True)
class ListChanges(Query[ChangesView]):
    """The last `limit` changes recorded (None: all), newest first."""

    limit: int | None = 20

    cacheable: ClassVar[bool] = False  # the log grows with every change
