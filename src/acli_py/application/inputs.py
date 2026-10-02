"""What someone wants an issue to look like, as they typed it: options, a CSV row, JSON.

`IssueInput` holds the values as typed ('@me', 'High', 'Story points=5'); the `IssueFields`
port turns it into the fields Jira takes, names resolved to ids.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

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


def known_key(name: str) -> str | None:
    """Return the `IssueInput` key a column or JSON key names ('Fix versions', 'due_date')."""
    return KNOWN_KEYS.get("".join(c for c in name.lower() if c not in " _-"))


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
            known = known_key(key)
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
