"""`JiraPeople` and `JiraProjects`: people and projects, over the client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from acli_py.domain.projects import DEFAULT_TEMPLATE, TEMPLATES, Component, Project, Version
from acli_py.infrastructure.jira import resolve
from acli_py.infrastructure.jira.client import API, NotFoundError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from acli_py.domain.projects import ProjectSpec
    from acli_py.infrastructure.jira.client import JiraClient

DETAILS = "lead,description,issueTypes,url,projectKeys"
# The schemes a project is given by id, read from the project itself: (field, path).
_OWN_SCHEMES = (
    ("permissionScheme", "permissionscheme"),
    ("notificationScheme", "notificationscheme"),
    ("issueSecurityScheme", "issuesecuritylevelscheme"),
)
# The schemes found by searching for the project: (field, path, key in each value).
_FOUND_SCHEMES = (
    ("issueTypeScheme", "issuetypescheme/project", "issueTypeScheme"),
    ("issueTypeScreenScheme", "issuetypescreenscheme/project", "issueTypeScreenScheme"),
    ("workflowScheme", "workflowscheme/project", "workflowScheme"),
)


class JiraPeople:
    """Finds people through the user search; '@me' is the logged-in user."""

    def __init__(self, client: JiraClient, me: Callable[[], str]) -> None:
        self.client = client
        self.me = me

    def account_id(self, who: str) -> str:
        """Return the account id of the one person `who` names."""
        if who.strip().lower() in resolve.ME:
            return self.me()
        return str(resolve.user(self.client, who)["accountId"])


class JiraProjects:
    """Reads and changes projects through a `JiraClient`."""

    def __init__(self, client: JiraClient) -> None:
        self.client = client

    def projects(self, *, query: str | None, status: str, limit: int | None) -> list[Project]:
        """Return a page or more of the project search, by key."""
        found = self.client.paged(
            f"{API}/project/search",
            limit=limit,
            query=query,
            orderBy="key",
            expand="lead",
            status=status,
        )
        return [Project.from_jira(p) for p in found]

    def recent(self) -> list[Project]:
        """Return the recently viewed projects."""
        return [
            Project.from_jira(p)
            for p in self.client.get(f"{API}/project/recent", expand="lead") or ()
        ]

    def project(self, key: str) -> Project:
        """Return the project in detail."""
        return Project.from_jira(self.client.get(f"{API}/project/{key}", expand=DETAILS))

    def components(self, key: str) -> list[Component]:
        """Return the components."""
        found = self.client.get(f"{API}/project/{key}/components") or ()
        return [Component.from_jira(c) for c in found]

    def versions(self, key: str) -> list[Version]:
        """Return the versions."""
        return [
            Version.from_jira(v) for v in self.client.get(f"{API}/project/{key}/versions") or ()
        ]

    def shared_configuration(self, key: str) -> dict[str, int]:
        """Return what a project sharing `key`'s configuration is created with."""
        data = self.client.get(f"{API}/project/{key}")
        source = Project.from_jira(data)
        if source.team_managed:
            raise ValueError(
                f"{key} is team-managed; only company-managed projects can share their "
                "configuration."
            )
        shared: dict[str, Any] = {"projectTypeKey": source.type or "software"}
        if category := (data.get("projectCategory") or {}).get("id"):
            shared["categoryId"] = int(category)
        for field_name, path in _OWN_SCHEMES:
            try:
                scheme = self.client.get(f"{API}/project/{key}/{path}")
            except NotFoundError:  # no issue security scheme, say
                continue
            if scheme and scheme.get("id") is not None:
                shared[field_name] = int(scheme["id"])
        for field_name, path, inner in _FOUND_SCHEMES:
            values = self.client.get(f"{API}/{path}", projectId=source.id).get("values") or []
            scheme_id = (values[0].get(inner) or {}).get("id") if values else None
            if scheme_id is not None:
                shared[field_name] = int(scheme_id)
        return shared

    def create(self, spec: ProjectSpec, lead: str, shared: Mapping[str, Any]) -> str:
        """Create the project; a template unless it shares another one's schemes."""
        body = _body(spec)
        body["leadAccountId"] = lead
        if shared:
            body.pop("projectTemplateKey", None)
            body.setdefault("projectTypeKey", shared["projectTypeKey"])
            body.update({k: v for k, v in shared.items() if k not in body})
        body.setdefault("projectTypeKey", "software")
        if not shared and "projectTemplateKey" not in body and body["projectTypeKey"] == "software":
            body["projectTemplateKey"] = TEMPLATES[DEFAULT_TEMPLATE][1]
        body.setdefault("assigneeType", "UNASSIGNED")
        return str((self.client.post(f"{API}/project", body) or {}).get("id", ""))

    def update(self, key: str, spec: ProjectSpec, lead: str | None) -> None:
        """Change the project."""
        body = _body(spec)
        if lead:
            body["leadAccountId"] = lead
        self.client.put(f"{API}/project/{key}", body)

    def delete(self, key: str, *, permanent: bool = False) -> None:
        """Delete the project, into the trash unless `permanent`."""
        self.client.delete(f"{API}/project/{key}", enableUndo="false" if permanent else "true")

    def archive(self, key: str) -> None:
        """Archive the project."""
        self.client.post(f"{API}/project/{key}/archive")

    def restore(self, key: str) -> None:
        """Restore the project."""
        self.client.post(f"{API}/project/{key}/restore")


def _body(spec: ProjectSpec) -> dict[str, Any]:
    """Return the project fields `spec` gives, as Jira takes them (no lead)."""
    body = {
        k: v for k in ("key", "name", "description", "url") if (v := getattr(spec, k)) is not None
    }
    type_key, template = spec.template_key()
    if template:
        body["projectTemplateKey"] = template
    if type_key or spec.type:
        body["projectTypeKey"] = type_key or spec.type
    body.update(spec.extra)
    return body
