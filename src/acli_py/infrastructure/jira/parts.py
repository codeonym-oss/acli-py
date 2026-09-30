"""`JiraComments`, `JiraAttachments` and `JiraWorklogs`: the parts of an issue, over the client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from acli_py.domain.issue import Attachment, Audience, Comment, Worklog
from acli_py.infrastructure.jira.client import API

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime
    from pathlib import Path

    from acli_py.infrastructure.jira.client import JiraClient


def _visibility(audience: Audience | None) -> dict[str, str] | None:
    return {"type": audience.kind, "value": audience.name} if audience else None


class JiraComments:
    """Reads and writes comments through a `JiraClient`."""

    def __init__(self, client: JiraClient) -> None:
        self.client = client

    def comments(
        self, key: str, *, newest_first: bool = False, limit: int | None = None
    ) -> list[Comment]:
        """Return the comments, a page at a time."""
        found = self.client.paged(
            f"{API}/issue/{key}/comment",
            key="comments",
            limit=limit,
            orderBy="-created" if newest_first else "created",
        )
        return [Comment.from_jira(c) for c in found]

    def comment(self, key: str, comment_id: str) -> Comment:
        """Return one comment."""
        return Comment.from_jira(self.client.get(f"{API}/issue/{key}/comment/{comment_id}"))

    def add(self, key: str, body: Mapping[str, Any], audience: Audience | None = None) -> str:
        """Add the comment."""
        payload: dict[str, Any] = {"body": dict(body)}
        if visibility := _visibility(audience):
            payload["visibility"] = visibility
        return str((self.client.post(f"{API}/issue/{key}/comment", payload) or {}).get("id", ""))

    def update(
        self,
        key: str,
        comment_id: str,
        body: Mapping[str, Any],
        audience: Audience | None = None,
        *,
        notify: bool = False,
    ) -> None:
        """Replace the comment's body."""
        payload: dict[str, Any] = {"body": dict(body)}
        if visibility := _visibility(audience):
            payload["visibility"] = visibility
        self.client.put(
            f"{API}/issue/{key}/comment/{comment_id}",
            payload,
            notifyUsers="true" if notify else "false",
        )

    def delete(self, key: str, comment_id: str) -> None:
        """Delete the comment."""
        self.client.delete(f"{API}/issue/{key}/comment/{comment_id}")

    def audiences(self, project: str | None = None) -> list[Audience]:
        """Return the project's roles, or the site's groups."""
        if project:
            roles = self.client.get(f"{API}/project/{project}/role") or {}
            return [Audience("role", name) for name in sorted(roles)]
        found = self.client.get(f"{API}/groups/picker", maxResults=100) or {}
        return [Audience("group", g["name"]) for g in found.get("groups", [])]


class JiraAttachments:
    """Uploads, downloads and deletes attachments through a `JiraClient`."""

    def __init__(self, client: JiraClient) -> None:
        self.client = client

    def attachments(self, key: str) -> list[Attachment]:
        """Return the issue's attachments."""
        found = self.client.issue(key, ["attachment"]).get("fields") or {}
        return [Attachment.from_jira(a) for a in found.get("attachment") or []]

    def attachment(self, attachment_id: str) -> Attachment:
        """Return the attachment's details."""
        return Attachment.from_jira(self.client.get(f"{API}/attachment/{attachment_id}"))

    def upload(self, key: str, path: Path) -> list[Attachment]:
        """Attach the file (a dry run answers with a plan, not a list)."""
        with path.open("rb") as handle:
            result = self.client.request(
                "POST",
                f"{API}/issue/{key}/attachments",
                files={"file": (path.name, handle)},
                headers={"X-Atlassian-Token": "no-check"},
            )
        return [Attachment.from_jira(a) for a in result] if isinstance(result, list) else []

    def download(self, attachment_id: str, dest: Path) -> int:
        """Save the content."""
        return self.client.download(f"{API}/attachment/content/{attachment_id}", dest)

    def delete(self, attachment_id: str) -> None:
        """Delete the attachment."""
        self.client.delete(f"{API}/attachment/{attachment_id}")


class JiraWorklogs:
    """Logs and reads work through a `JiraClient`."""

    def __init__(self, client: JiraClient) -> None:
        self.client = client

    def worklogs(self, key: str) -> list[Worklog]:
        """Return the issue's worklogs."""
        found = self.client.paged(f"{API}/issue/{key}/worklog", key="worklogs")
        return [Worklog.from_jira(w) for w in found]

    def worklog(self, key: str, worklog_id: str) -> Worklog:
        """Return one worklog."""
        return Worklog.from_jira(self.client.get(f"{API}/issue/{key}/worklog/{worklog_id}"))

    def log(
        self,
        key: str,
        spent: str,
        comment: Mapping[str, Any] | None = None,
        started: datetime | None = None,
        remaining: str = "",
    ) -> str:
        """Log the work; Jira adjusts the remaining estimate itself unless given one."""
        body: dict[str, Any] = {"timeSpent": spent}
        if comment:
            body["comment"] = dict(comment)
        if started is not None:
            body["started"] = jira_time(started)
        params = {"adjustEstimate": "new", "newEstimate": remaining} if remaining else {}
        return str(
            (self.client.post(f"{API}/issue/{key}/worklog", body, **params) or {}).get("id", "")
        )

    def delete(self, key: str, worklog_id: str) -> None:
        """Delete the worklog."""
        self.client.delete(f"{API}/issue/{key}/worklog/{worklog_id}")


def jira_time(moment: datetime) -> str:
    """Return a moment as Jira's worklog timestamp: '2026-09-24T09:00:00.000+0200'."""
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000%z")
