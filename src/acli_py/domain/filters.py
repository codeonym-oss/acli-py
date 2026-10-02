"""Saved filters, the columns they show, and dashboards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from acli_py.domain.issue import User

if TYPE_CHECKING:
    from collections.abc import Mapping


def _shared_with(permission: Mapping[str, Any]) -> str:
    """Return who one share permission reaches: a group, a project, or its kind ('global')."""
    for kind, member in (("group", "name"), ("project", "key"), ("role", "name")):
        if isinstance(permission.get(kind), dict) and permission[kind].get(member):
            return str(permission[kind][member])
    return str(permission.get("type", ""))


@dataclass(frozen=True)
class Filter:
    """A saved JQL query."""

    id: str
    name: str
    jql: str = ""
    owner: User | None = None
    description: str = ""
    favourite: bool = False
    shared_with: tuple[str, ...] = ()
    url: str = ""

    @classmethod
    def from_jira(cls, data: Mapping[str, Any], *, favourite: bool | None = None) -> Filter:
        """Read a filter from Jira's JSON; `favourite` says so when Jira's JSON doesn't."""
        shares = (_shared_with(p) for p in data.get("sharePermissions") or ())
        return cls(
            str(data.get("id", "")),
            data.get("name", ""),
            data.get("jql") or "",
            User.from_jira(data.get("owner")),
            data.get("description") or "",
            bool(data.get("favourite")) if favourite is None else favourite,
            tuple(s for s in shares if s),
            data.get("viewUrl") or "",
        )


@dataclass(frozen=True)
class FilterColumn:
    """A column a filter shows in the issue navigator."""

    field: str
    label: str = ""


@dataclass(frozen=True)
class Dashboard:
    """A dashboard."""

    id: str
    name: str
    owner: User | None = None
    description: str = ""
    favourite: bool = False
    popularity: int = 0
    url: str = ""

    @classmethod
    def from_jira(cls, data: Mapping[str, Any]) -> Dashboard:
        """Read a dashboard from Jira's JSON."""
        return cls(
            str(data.get("id", "")),
            data.get("name", ""),
            User.from_jira(data.get("owner")),
            data.get("description") or "",
            bool(data.get("isFavourite")),
            int(data.get("popularity") or 0),
            data.get("view") or "",
        )
