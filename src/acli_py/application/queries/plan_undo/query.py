from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from mediary.cqrs import Query, query

from acli_py.application.queries.plan_undo.view import UndoPlan


@query
@dataclass(frozen=True)
class PlanUndo(Query[UndoPlan]):
    """How to reverse record `entry_id`, or (None) the last change not undone yet."""

    entry_id: str | None = None

    cacheable: ClassVar[bool] = False  # it reads the issues as they are now
