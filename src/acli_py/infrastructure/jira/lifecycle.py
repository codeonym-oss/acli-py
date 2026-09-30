"""`JiraStore` and `JiraLinks`: the `IssueStore`, `Destination` and `IssueLinks` ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from acli_py.infrastructure.jira.client import API

if TYPE_CHECKING:
    from collections.abc import Mapping

    from acli_py.infrastructure.jira.client import JiraClient


class JiraStore:
    """Creates, deletes and archives issues through a `JiraClient`.

    As a `Destination`, it is `elsewhere` when it works on another site than the user's own.
    """

    def __init__(self, client: JiraClient, url: str, *, elsewhere: bool = False) -> None:
        self.client = client
        self.url = url
        self.elsewhere = elsewhere

    def create(self, fields: Mapping[str, Any], update: Mapping[str, Any]) -> str:
        """Create the issue and return its key."""
        body: dict[str, Any] = {"fields": dict(fields)}
        if update:
            body["update"] = dict(update)
        return str(self.client.post(f"{API}/issue", body)["key"])

    def delete(self, key: str, *, subtasks: bool = False) -> None:
        """Delete the issue."""
        self.client.delete(f"{API}/issue/{key}", deleteSubtasks="true" if subtasks else None)

    def archive(self, key: str, *, archive: bool = True) -> None:
        """Archive or restore the issue; Jira reports refusals in the body, not the status."""
        path = f"{API}/issue/{'archive' if archive else 'unarchive'}"
        result = self.client.put(path, {"issueIdsOrKeys": [key]}) or {}
        for error in (result.get("errors") or {}).values():
            raise ValueError(error.get("message") or "Jira refused.")

    def web_link(self, key: str, url: str, title: str) -> None:
        """Add a web link to the issue."""
        self.client.post(f"{API}/issue/{key}/remotelink", {"object": {"url": url, "title": title}})


class JiraLinks:
    """Links issues through a `JiraClient`."""

    def __init__(self, client: JiraClient) -> None:
        self.client = client

    def link_type(self, name: str) -> str | None:
        """Return the type's name as the site spells it."""
        wanted = name.lower()
        return next(
            (t["name"] for t in self.client.link_types() if t.get("name", "").lower() == wanted),
            None,
        )

    def link(self, type_name: str, outward: str, inward: str) -> None:
        """Link the two issues."""
        self.client.post(
            f"{API}/issueLink",
            {
                "type": {"name": type_name},
                "outwardIssue": {"key": outward},
                "inwardIssue": {"key": inward},
            },
        )
