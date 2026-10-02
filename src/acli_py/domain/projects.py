"""Projects as Jira has them: their details, components and versions, and how one is made."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from acli_py.domain.issue import User
from acli_py.domain.values import day

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

GREENHOPPER = "com.pyxis.greenhopper.jira:gh-simplified-"
CORE = "com.atlassian.jira-core-project-templates:jira-core-simplified-"
# Friendly names for Jira's company-managed project templates: name → (type, template key).
TEMPLATES: dict[str, tuple[str, str]] = {
    "scrum": ("software", f"{GREENHOPPER}scrum-classic"),
    "kanban": ("software", f"{GREENHOPPER}kanban-classic"),
    "basic": ("software", f"{GREENHOPPER}basic"),
    "tasks": ("business", f"{CORE}task-tracking"),
    "process": ("business", f"{CORE}process-control"),
    "service": ("service_desk", "com.atlassian.servicedesk:simplified-it-service-management"),
}
DEFAULT_TEMPLATE = "kanban"


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class Component:
    """A part of a project issues can belong to."""

    id: str
    name: str
    lead: User | None = None
    description: str = ""

    @classmethod
    def from_jira(cls, data: Mapping[str, Any]) -> Component:
        """Read a component from Jira's JSON."""
        return cls(
            str(data.get("id", "")),
            data.get("name", ""),
            User.from_jira(data.get("lead")),
            data.get("description") or "",
        )


@dataclass(frozen=True)
class Version:
    """A release of a project."""

    id: str
    name: str
    released: bool = False
    archived: bool = False
    start: date | None = None
    release: date | None = None
    description: str = ""

    @classmethod
    def from_jira(cls, data: Mapping[str, Any]) -> Version:
        """Read a version from Jira's JSON."""
        return cls(
            str(data.get("id", "")),
            data.get("name", ""),
            bool(data.get("released")),
            bool(data.get("archived")),
            day(data.get("startDate")),
            day(data.get("releaseDate")),
            data.get("description") or "",
        )


@dataclass(frozen=True)
class Project:
    """A project, with as much detail as Jira sent."""

    key: str
    name: str = ""
    id: str = ""
    type: str = ""
    style: str = ""
    lead: User | None = None
    category: str = ""
    url: str = ""
    description: str = ""
    issue_types: tuple[str, ...] = ()
    components: tuple[Component, ...] = ()
    versions: tuple[Version, ...] = ()

    @property
    def team_managed(self) -> bool:
        """Return whether Jira manages the project's configuration for its team (next-gen)."""
        return self.style == "next-gen"

    @classmethod
    def from_jira(cls, data: Mapping[str, Any]) -> Project:
        """Read a project from Jira's JSON."""
        return cls(
            key=data.get("key", ""),
            name=data.get("name", ""),
            id=str(data.get("id", "")),
            type=data.get("projectTypeKey", ""),
            style="next-gen" if data.get("simplified") else data.get("style", ""),
            lead=User.from_jira(data.get("lead")),
            category=_dict(data.get("projectCategory")).get("name", ""),
            url=data.get("url") or "",
            description=data.get("description") or "",
            issue_types=tuple(t.get("name", "") for t in data.get("issueTypes") or ()),
            components=tuple(Component.from_jira(c) for c in data.get("components") or ()),
            versions=tuple(Version.from_jira(v) for v in data.get("versions") or ()),
        )


@dataclass(frozen=True)
class ProjectSpec:
    """What a project should be: what to create, or what to change (None: leave it).

    `template` is a friendly name from `TEMPLATES` or a full Jira template key. `lead` is a
    person as the user wrote them ('@me', an email). `extra` holds any other of Jira's own
    project fields, passed through as they are.
    """

    key: str | None = None
    name: str | None = None
    description: str | None = None
    url: str | None = None
    lead: str | None = None
    template: str | None = None
    type: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    KNOWN = ("key", "name", "description", "url", "lead", "template", "type")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> ProjectSpec:
        """Return the spec a JSON file or the options describe; unknown members go in `extra`."""
        given = {k: data[k] for k in cls.KNOWN if data.get(k) is not None}
        if given.get("key"):
            given["key"] = str(given["key"]).upper()
        extra = {k: v for k, v in data.items() if k not in cls.KNOWN}
        return cls(**given, extra=extra)

    @property
    def empty(self) -> bool:
        """Return whether the spec changes nothing."""
        return not self.extra and all(getattr(self, k) is None for k in self.KNOWN)

    def template_key(self) -> tuple[str | None, str | None]:
        """Return the project type and Jira template key `template` names (None, None: none)."""
        if not self.template:
            return None, None
        type_key, template = TEMPLATES.get(self.template.lower(), (None, self.template))
        return self.type or type_key, template
