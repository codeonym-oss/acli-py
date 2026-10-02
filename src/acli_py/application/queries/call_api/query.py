from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from mediary.cqrs import Query, query


@query
@dataclass(frozen=True)
class ApiGet(Query[Any]):
    """GET `path` with `params` (each a name and its values) and return the JSON."""

    path: str
    params: tuple[tuple[str, tuple[str, ...]], ...] = ()

    cacheable: ClassVar[bool] = False  # what is asked for by hand is wanted fresh
