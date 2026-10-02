"""The site's own lists (statuses, priorities, resolutions, issue types) and people's profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from acli_py.domain.issue import StatusCategory, User

if TYPE_CHECKING:
    from collections.abc import Mapping


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class Named:
    """An entry of a plain list: a priority or a resolution."""

    id: str
    name: str
    description: str = ""

    @classmethod
    def from_jira(cls, data: Mapping[str, Any]) -> Named:
        """Read an entry from Jira's JSON."""
        return cls(str(data.get("id", "")), data.get("name", ""), data.get("description") or "")


@dataclass(frozen=True)
class StatusInfo:
    """A status of the site, its category, and the project it belongs to (team-managed)."""

    id: str
    name: str
    category: StatusCategory = StatusCategory.UNKNOWN
    category_name: str = ""
    project_id: str = ""

    @classmethod
    def from_jira(cls, data: Mapping[str, Any]) -> StatusInfo:
        """Read a status from Jira's JSON."""
        category = _dict(data.get("statusCategory"))
        try:
            kind = StatusCategory(category.get("key", ""))
        except ValueError:
            kind = StatusCategory.UNKNOWN
        project = _dict(_dict(data.get("scope")).get("project")).get("id", "")
        return cls(str(data.get("id", "")), data.get("name", ""), kind,
                   category.get("name", ""), str(project))  # fmt: skip


@dataclass(frozen=True)
class IssueTypeInfo:
    """An issue type: whether it is a subtask, and its level (1 epic, 0 standard, -1 subtask)."""

    id: str
    name: str
    subtask: bool = False
    level: int = 0
    description: str = ""

    @classmethod
    def from_jira(cls, data: Mapping[str, Any]) -> IssueTypeInfo:
        """Read an issue type from Jira's JSON."""
        return cls(str(data.get("id", "")), data.get("name", ""), bool(data.get("subtask")),
                   int(data.get("hierarchyLevel") or 0), data.get("description") or "")  # fmt: skip


@dataclass(frozen=True)
class Profile:
    """A person's profile: who they are, their kind of account, where, and their groups."""

    user: User
    account_type: str = ""
    time_zone: str = ""
    locale: str = ""
    groups: tuple[str, ...] = ()

    @classmethod
    def from_jira(cls, data: Mapping[str, Any]) -> Profile:
        """Read a profile from Jira's JSON."""
        user = User.from_jira(data) or User("", data.get("displayName", ""))
        groups = tuple(
            g["name"] for g in _dict(data.get("groups")).get("items") or () if "name" in g
        )
        return cls(user, data.get("accountType", ""), data.get("timeZone") or "",
                   data.get("locale") or "", groups)  # fmt: skip
