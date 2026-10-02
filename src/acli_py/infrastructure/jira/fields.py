"""Building issue field payloads: `IssueInput` into the fields Jira takes (`JiraIssueFields`).

`text` and `when` live in `acli_py.domain.values`; they are re-exported for older callers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from acli_py.application.inputs import IssueInput as IssueInput
from acli_py.application.inputs import known_key
from acli_py.domain import adf
from acli_py.domain.values import text as text
from acli_py.domain.values import when as when
from acli_py.infrastructure.jira import resolve

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from acli_py.infrastructure.jira.client import JiraClient


def build(
    client: JiraClient,
    wanted: IssueInput,
    *,
    me: str | None = None,
    creating: bool = False,
    catalog: resolve.FieldCatalog | None = None,
) -> dict[str, Any]:
    """Return the `fields` payload for creating or editing an issue."""
    if wanted.raw:
        return dict(wanted.raw.get("fields", {}))
    fields: dict[str, Any] = {}
    if wanted.project:
        fields["project"] = {"key": wanted.project.upper()}
    if wanted.type:
        fields["issuetype"] = (
            {"id": wanted.type} if wanted.type.isdigit() else {"name": wanted.type}
        )
    if wanted.summary is not None:
        fields["summary"] = wanted.summary.strip()
    if wanted.description is not None:
        fields["description"] = adf.to_adf(wanted.description) if wanted.description else None
    if wanted.assignee is not None:
        who = resolve.account_id(client, wanted.assignee, me)
        # Omitting the assignee on create leaves the project's default assignee to Jira.
        if not (creating and who == "-1"):
            fields["assignee"] = {"accountId": who} if who else None
    if wanted.reporter is not None:
        fields["reporter"] = {"accountId": resolve.user(client, wanted.reporter, me)["accountId"]}
    if wanted.labels is not None:
        fields["labels"] = wanted.labels
    if wanted.components is not None:
        fields["components"] = [{"name": c} for c in wanted.components]
    if wanted.fix_versions is not None:
        fields["fixVersions"] = [{"name": v} for v in wanted.fix_versions]
    if wanted.priority:
        fields["priority"] = (
            {"id": wanted.priority} if wanted.priority.isdigit() else {"name": wanted.priority}
        )
    if wanted.parent:
        fields["parent"] = {"key": wanted.parent.upper()}
    if wanted.due is not None:
        fields["duedate"] = wanted.due or None
    fields.update(resolve.field_values(client, wanted.extra, me, catalog))
    return fields


# The field each friendly key of `IssueInput` fills.
FIELD_OF = {
    "project": "project",
    "type": "issuetype",
    "summary": "summary",
    "description": "description",
    "assignee": "assignee",
    "reporter": "reporter",
    "labels": "labels",
    "components": "components",
    "fix_versions": "fixVersions",
    "priority": "priority",
    "parent": "parent",
    "due": "duedate",
}


class JiraIssueFields:
    """The `IssueFields` port: `IssueInput` and `build`, with the site's field catalog."""

    def __init__(self, client: JiraClient, me: Callable[[], str]) -> None:
        self.client = client
        self.me = me
        self._catalog: resolve.FieldCatalog | None = None

    @property
    def catalog(self) -> resolve.FieldCatalog:
        """Return the site's fields, read once."""
        if self._catalog is None:
            self._catalog = resolve.FieldCatalog.load(self.client)
        return self._catalog

    def build(self, row: Mapping[str, Any], *, creating: bool = False) -> dict[str, Any]:
        """Return the fields the row sets."""
        return self.fields_for(IssueInput.from_mapping(dict(row)), creating=creating)

    def fields_for(self, wanted: IssueInput, *, creating: bool = False) -> dict[str, Any]:
        """Return the fields `wanted` sets."""
        catalog = self.catalog if wanted.extra else None
        return build(self.client, wanted, me=self.me(), creating=creating, catalog=catalog)

    def field_values(self, assignments: tuple[str, ...]) -> dict[str, Any]:
        """Return the fields the assignments set."""
        if not assignments:
            return {}
        return resolve.field_values(self.client, list(assignments), self.me(), self.catalog)

    def field_of(self, column: str) -> str:
        """Return the field a column fills: a friendly key's, else the one so named."""
        known = known_key(column)
        if known:
            return FIELD_OF[known]
        return str(self.catalog.find(column)["id"])
