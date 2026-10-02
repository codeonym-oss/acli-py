from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from mediary.cqrs import Query, query

from acli_py.application.queries.plan_import.view import ImportPlan


@query
@dataclass(frozen=True)
class PlanImport(Query[ImportPlan]):
    """What importing `rows` would do: update the issues they name by key, create the rest.

    New issues go to `project` and are of `issue_type` unless their row says otherwise.
    """

    rows: tuple[Mapping[str, Any], ...]
    project: str | None = None
    issue_type: str = "Task"

    cacheable: ClassVar[bool] = False  # it reads the issues as they are now
