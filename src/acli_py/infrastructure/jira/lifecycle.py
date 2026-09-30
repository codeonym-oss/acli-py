"""`JiraStore` and `JiraLinks`: the `IssueStore`, `Destination` and `IssueLinks` ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from acli_py.domain.issue import Link
from acli_py.domain.links import IssueLink, LinkType
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

    def link_types(self) -> tuple[LinkType, ...]:
        """Return the site's link types."""
        return tuple(LinkType.from_jira(t) for t in self.client.link_types())

    def links_of(self, key: str) -> tuple[Link, ...]:
        """Return the issue's links."""
        found = self.client.issue(key, ["issuelinks"]).get("fields") or {}
        return tuple(link for link in map(Link.from_jira, found.get("issuelinks") or []) if link)

    def get_link(self, link_id: str) -> IssueLink:
        """Return the link."""
        return IssueLink.from_jira(self.client.get(f"{API}/issueLink/{link_id}"))

    def link(self, link: IssueLink, comment: Mapping[str, Any] | None = None) -> None:
        """Store the link (POST /issueLink returns nothing, not even the new id)."""
        body = link.to_jira()
        if comment:
            body["comment"] = {"body": dict(comment)}
        self.client.post(f"{API}/issueLink", body)

    def unlink(self, link_id: str) -> None:
        """Remove the link."""
        self.client.delete(f"{API}/issueLink/{link_id}")
