"""`JiraIssues`: the `IssueReader` port, backed by the Jira REST client."""

from __future__ import annotations

from typing import TYPE_CHECKING

from acli_py.domain.issue import KNOWN_FIELDS, Issue

if TYPE_CHECKING:
    from acli_py.infrastructure.jira.client import JiraClient

ALL = "*all"


class JiraIssues:
    """Reads issues through a `JiraClient` and parses them into domain objects."""

    def __init__(self, client: JiraClient, url: str) -> None:
        self.client = client
        self.url = url.rstrip("/")

    def get_issue(self, key: str, fields: tuple[str, ...] = ()) -> Issue:
        """Return the issue with the detail fields, plus `fields` ('*all' for every field)."""
        wanted = [ALL] if ALL in fields else [*sorted(KNOWN_FIELDS), *fields]
        data = self.client.issue(key, wanted, expand="names" if fields else None)
        return Issue.from_jira(data)

    def browse_url(self, key: str) -> str:
        """Return the issue's page on the site."""
        return f"{self.url}/browse/{key}"
