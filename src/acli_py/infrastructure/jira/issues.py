"""`JiraIssues` and `JiraSearch`: the `IssueReader` and `IssueSearch` ports, over REST."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from acli_py.domain.history import HistoryEntry
from acli_py.domain.issue import KNOWN_FIELDS, Issue
from acli_py.infrastructure.jira.client import API, SEARCH_PAGE_SIZE

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

    def history(self, key: str) -> list[HistoryEntry]:
        """Return the issue's changelog, oldest first."""
        entries = self.client.paged(f"{API}/issue/{key}/changelog", limit=None)
        return [HistoryEntry.from_jira(e) for e in entries]


class JiraSearch:
    """Runs JQL searches, a page at a time, through `POST /search/jql`."""

    def __init__(self, client: JiraClient) -> None:
        self.client = client

    def search(
        self, jql: str, fields: tuple[str, ...], *, limit: int | None, token: str | None = None
    ) -> tuple[list[Issue], str | None]:
        """Return up to `limit` issues (None: all) from `token` on, and the token after them."""
        found: list[Issue] = []
        while limit is None or len(found) < limit:
            size = SEARCH_PAGE_SIZE if limit is None else min(SEARCH_PAGE_SIZE, limit - len(found))
            body: dict[str, Any] = {"jql": jql, "maxResults": size, "fields": list(fields)}
            if token:
                body["nextPageToken"] = token
            data = self.client.post(f"{API}/search/jql", body)
            found.extend(Issue.from_jira(i) for i in data.get("issues") or ())
            token = None if data.get("isLast", False) else data.get("nextPageToken")
            if not token:
                break
        return found, token

    def count(self, jql: str) -> int:
        """Return Jira's approximate count of issues matching `jql`."""
        return self.client.count(jql)

    def filter_jql(self, filter_id: str) -> str:
        """Return the JQL the saved filter runs."""
        return str(self.client.filter(filter_id).get("jql") or "")

    def problems(self, jql: str) -> list[str]:
        """Return Jira's complaints about the query."""
        return self.client.validate_jql(jql)
