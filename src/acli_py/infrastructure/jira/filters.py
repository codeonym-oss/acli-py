"""`JiraFilters`, `JiraFields` and `JiraDashboards`: filters, fields and dashboards."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from acli_py.domain.fields import FieldInfo
from acli_py.domain.filters import Dashboard, Filter, FilterColumn
from acli_py.infrastructure.jira.client import API

if TYPE_CHECKING:
    from collections.abc import Mapping

    from acli_py.infrastructure.jira.client import JiraClient


class JiraFilters:
    """Reads and changes saved filters through a `JiraClient`."""

    def __init__(self, client: JiraClient) -> None:
        self.client = client

    def mine(self) -> list[Filter]:
        """Return the user's own filters."""
        found = self.client.get(f"{API}/filter/my", expand="favourite") or ()
        return [Filter.from_jira(f) for f in found]

    def favourites(self) -> list[Filter]:
        """Return the starred filters."""
        found = self.client.get(f"{API}/filter/favourite") or ()
        return [Filter.from_jira(f, favourite=True) for f in found]

    def search(
        self, *, name: str | None, owner: str | None, project: str | None, limit: int | None
    ) -> list[Filter]:
        """Return the filters matching what is given."""
        project_id = self.client.get(f"{API}/project/{project}")["id"] if project else None
        found = self.client.paged(
            f"{API}/filter/search",
            limit=limit,
            filterName=name,
            accountId=owner,
            projectId=project_id,
            expand="owner,jql,favourite",
            orderBy="name",
        )
        return [Filter.from_jira(f) for f in found]

    def filter(self, filter_id: str) -> Filter:
        """Return the filter."""
        return Filter.from_jira(
            self.client.get(f"{API}/filter/{filter_id}", expand="sharedUsers,subscriptions")
        )

    def create(
        self,
        name: str,
        jql: str,
        description: str | None,
        favourite: bool,
        shares: tuple[Mapping[str, Any], ...] | None,
    ) -> str:
        """Save the filter."""
        body: dict[str, Any] = {"name": name, "jql": jql, "favourite": favourite}
        if description:
            body["description"] = description
        if shares is not None:
            body["sharePermissions"] = [dict(s) for s in shares]
        return str((self.client.post(f"{API}/filter", body) or {}).get("id", ""))

    def update(
        self,
        filter_id: str,
        *,
        name: str,
        jql: str | None = None,
        description: str | None = None,
        shares: tuple[Mapping[str, Any], ...] | None = None,
        edit_shares: tuple[Mapping[str, Any], ...] | None = None,
    ) -> None:
        """Change the filter."""
        body: dict[str, Any] = {"name": name}
        if jql is not None:
            body["jql"] = jql
        if description is not None:
            body["description"] = description
        if shares is not None:
            body["sharePermissions"] = [dict(s) for s in shares]
        if edit_shares is not None:
            body["editPermissions"] = [dict(s) for s in edit_shares]
        self.client.put(f"{API}/filter/{filter_id}", body)

    def delete(self, filter_id: str) -> None:
        """Delete the filter."""
        self.client.delete(f"{API}/filter/{filter_id}")

    def star(self, filter_id: str, *, star: bool = True) -> None:
        """Star or unstar the filter."""
        path = f"{API}/filter/{filter_id}/favourite"
        if star:
            self.client.put(path)
        else:
            self.client.delete(path)

    def give(self, filter_id: str, account_id: str) -> None:
        """Change the filter's owner."""
        self.client.put(f"{API}/filter/{filter_id}/owner", {"accountId": account_id})

    def columns(self, filter_id: str) -> list[FilterColumn]:
        """Return the filter's columns."""
        found = self.client.get(f"{API}/filter/{filter_id}/columns") or ()
        return [FilterColumn(c.get("value", ""), c.get("label", "")) for c in found]

    def set_columns(self, filter_id: str, fields: tuple[str, ...]) -> None:
        """Set the columns, or reset them."""
        path = f"{API}/filter/{filter_id}/columns"
        if fields:
            self.client.put(path, {"columns": list(fields)})
        else:
            self.client.delete(path)


class JiraFields:
    """Reads the site's fields and changes its custom fields through a `JiraClient`."""

    def __init__(self, client: JiraClient) -> None:
        self.client = client

    def fields(self) -> list[FieldInfo]:
        """Return every field."""
        return [FieldInfo.from_jira(f) for f in self.client.fields()]

    def trashed(self, query: str | None) -> list[FieldInfo]:
        """Return the custom fields in the trash."""
        found = self.client.paged(f"{API}/field/search/trashed", query=query)
        return [FieldInfo.from_jira(f) for f in found]

    def create(self, name: str, type: str, searcher: str | None, description: str | None) -> str:
        """Create the custom field."""
        body = {"name": name, "type": type, "searcherKey": searcher, "description": description}
        created = self.client.post(f"{API}/field", {k: v for k, v in body.items() if v})
        return str((created or {}).get("id", ""))

    def update(
        self, field_id: str, *, name: str | None, description: str | None, searcher: str | None
    ) -> None:
        """Change the custom field."""
        body = {"name": name, "description": description, "searcherKey": searcher}
        self.client.put(f"{API}/field/{field_id}", {k: v for k, v in body.items() if v is not None})

    def trash(self, field_id: str) -> None:
        """Trash the custom field."""
        self.client.post(f"{API}/field/{field_id}/trash")

    def restore(self, field_id: str) -> None:
        """Restore the custom field."""
        self.client.post(f"{API}/field/{field_id}/restore")


class JiraDashboards:
    """Finds dashboards through a `JiraClient`."""

    def __init__(self, client: JiraClient) -> None:
        self.client = client

    def search(self, *, name: str | None, owner: str | None, limit: int | None) -> list[Dashboard]:
        """Return the dashboards matching what is given."""
        found = self.client.paged(
            f"{API}/dashboard/search",
            limit=limit,
            dashboardName=name,
            accountId=owner,
            expand="owner,favourite",
            orderBy="name",
        )
        return [Dashboard.from_jira(d) for d in found]

    def dashboard(self, dashboard_id: str) -> Dashboard:
        """Return the dashboard."""
        return Dashboard.from_jira(self.client.get(f"{API}/dashboard/{dashboard_id}"))
