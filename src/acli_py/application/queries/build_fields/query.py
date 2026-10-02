from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from mediary.cqrs import Query, query

from acli_py.application.inputs import IssueInput


@query
@dataclass(frozen=True)
class BuildFields(Query[dict[str, Any]]):
    """The fields `wanted` sets, as Jira takes them; a new issue's when `creating`."""

    wanted: IssueInput = field(compare=False)
    creating: bool = False

    cacheable: ClassVar[bool] = False  # its input isn't a cache key


@query
@dataclass(frozen=True)
class ResolveFieldValues(Query[dict[str, Any]]):
    """{field id: value} for 'Story points=5' and 'NAME:=JSON' assignments."""

    assignments: tuple[str, ...] = ()
