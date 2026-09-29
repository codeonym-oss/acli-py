"""Building issue field payloads.

`text` and `when` live in `acli_py.domain.values`; they are re-exported for older callers.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from acli_py.domain import adf
from acli_py.domain.values import text as text
from acli_py.domain.values import when as when
from acli_py.infrastructure.jira import resolve

if TYPE_CHECKING:
    from pathlib import Path

    from acli_py.infrastructure.jira.client import JiraClient

# Keys `acli-py issue create --from-json/--from-csv` understands; anything else is a field name.
KNOWN_KEYS = {
    "project": "project",
    "projectkey": "project",
    "type": "type",
    "issuetype": "type",
    "summary": "summary",
    "description": "description",
    "assignee": "assignee",
    "reporter": "reporter",
    "labels": "labels",
    "label": "labels",
    "components": "components",
    "component": "components",
    "fixversions": "fix_versions",
    "fixversion": "fix_versions",
    "priority": "priority",
    "parent": "parent",
    "parentissueid": "parent",
    "due": "due",
    "duedate": "due",
}

TEMPLATE = {
    "project": "DEMO",
    "type": "Task",
    "summary": "Write the release notes",
    "description": "What changed, **for whom**, and how to upgrade.\n\n- one\n- two",
    "assignee": "@me",
    "priority": "Medium",
    "labels": ["docs", "release"],
    "components": [],
    "parent": None,
    "due": "2026-12-31",
    "fields": {"Story point estimate": 3},
}


@dataclass
class IssueInput:
    """What someone wants an issue to look like, as they typed it."""

    project: str | None = None
    type: str | None = None
    summary: str | None = None
    description: str | None = None
    assignee: str | None = None
    reporter: str | None = None
    labels: list[str] | None = None
    components: list[str] | None = None
    fix_versions: list[str] | None = None
    priority: str | None = None
    parent: str | None = None
    due: str | None = None
    extra: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> IssueInput:
        """Build from a JSON object or CSV row using friendly keys (see TEMPLATE).

        An object shaped like Jira's own payload (`{"fields": {"project": …}}`) is passed
        through untouched.
        """
        if isinstance(data.get("fields"), dict) and "project" in data["fields"]:
            return cls(raw=data)
        result = cls()
        for key, value in data.items():
            if value in (None, "", []):
                continue
            known = KNOWN_KEYS.get(key.replace("_", "").replace("-", "").lower())
            if key == "fields" and isinstance(value, dict):
                for name, inner in value.items():
                    result.extra.append(
                        f"{name}={inner}"
                        if isinstance(inner, (str, int, float))
                        else f"{name}:={json.dumps(inner)}"
                    )
            elif known in ("labels", "components", "fix_versions"):
                items = value if isinstance(value, list) else split_list(str(value))
                setattr(result, known, [str(v) for v in items])
            elif known:
                setattr(result, known, str(value))
            else:
                result.extra.append(f"{key}={value}")
        return result


def split_list(text: str) -> list[str]:
    """Split 'a, b;c' into ['a', 'b', 'c']."""
    return [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]


def flat(values: list[str] | None) -> list[str] | None:
    """Flatten repeated, comma-separated options."""
    if values is None:
        return None
    return [item for value in values for item in split_list(value)]


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


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Read issues from a JSON file (an object or a list) or a CSV file with a header row."""
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".csv":
        return [dict(row) for row in csv.DictReader(text.splitlines())]
    data = json.loads(text)
    if isinstance(data, dict) and isinstance(data.get("issues"), list):
        data = data["issues"]
    if isinstance(data, dict) and isinstance(data.get("issueUpdates"), list):
        data = data["issueUpdates"]
    return data if isinstance(data, list) else [data]
