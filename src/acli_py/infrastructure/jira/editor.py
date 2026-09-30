"""`JiraEditor` and `JiraWatchers`: the `IssueEditor` and `Watchers` ports, over the client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from acli_py.infrastructure.jira.client import API

if TYPE_CHECKING:
    from collections.abc import Mapping

    from acli_py.infrastructure.jira.client import JiraClient


class JiraEditor:
    """Reads and changes an issue's fields through a `JiraClient`."""

    def __init__(self, client: JiraClient) -> None:
        self.client = client

    def values(self, key: str, field_ids: tuple[str, ...]) -> dict[str, Any]:
        """Return the fields' values now."""
        found = self.client.issue(key, list(field_ids)).get("fields") or {}
        return {field_id: found.get(field_id) for field_id in field_ids}

    def edit(
        self,
        key: str,
        fields: Mapping[str, Any],
        update: Mapping[str, Any],
        *,
        notify: bool = True,
    ) -> None:
        """Send one edit with the fields and the operations."""
        body: dict[str, Any] = {}
        if fields:
            body["fields"] = dict(fields)
        if update:
            body["update"] = dict(update)
        if body:
            self.client.put(f"{API}/issue/{key}", body, notifyUsers=None if notify else "false")

    def assign(self, key: str, account_id: str | None) -> None:
        """Set or clear the assignee."""
        self.client.put(f"{API}/issue/{key}/assignee", {"accountId": account_id})


class JiraWatchers:
    """Reads and changes an issue's watchers through a `JiraClient`."""

    def __init__(self, client: JiraClient) -> None:
        self.client = client

    def watching(self, key: str, account_id: str) -> bool:
        """Return whether the person is among the watchers."""
        found = self.client.get(f"{API}/issue/{key}/watchers") or {}
        return any(w.get("accountId") == account_id for w in found.get("watchers") or [])

    def watch(self, key: str, account_id: str, *, watch: bool = True) -> None:
        """Add or remove the watcher."""
        if watch:
            self.client.post(f"{API}/issue/{key}/watchers", account_id)
        else:
            self.client.delete(f"{API}/issue/{key}/watchers", accountId=account_id)
