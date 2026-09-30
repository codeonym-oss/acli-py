"""What a copy of an issue takes from the original.

A copy keeps the summary (with a prefix), description, type, priority, labels, due date and
environment. Components, fix versions and the parent belong to the original's project, so
they are kept only when the copy stays in it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

# The fields a copy is made from.
COPIED = (
    "summary", "description", "issuetype", "priority", "labels", "components", "duedate",
    "environment", "parent", "project", "fixVersions",
)  # fmt: skip


def copy_of(
    original: Mapping[str, Any], *, project: str = "", prefix: str = "", same_site: bool = True
) -> dict[str, Any]:
    """Return the fields to create a copy of an issue with `original`'s fields (as Jira has them).

    `project` is where the copy goes (default: the original's); `same_site` False means another
    site, whose projects share nothing with this one's.
    """
    here = original["project"]["key"]
    target = (project or here).upper()
    fields: dict[str, Any] = {
        "project": {"key": target},
        "summary": prefix + (original.get("summary") or ""),
        "issuetype": {"name": original["issuetype"]["name"]},
    }
    for name in ("description", "labels", "duedate", "environment"):
        if original.get(name):
            fields[name] = original[name]
    if original.get("priority"):
        fields["priority"] = {"name": original["priority"]["name"]}
    if same_site and target == here:
        if original.get("components"):
            fields["components"] = [{"id": c["id"]} for c in original["components"]]
        if original.get("fixVersions"):
            fields["fixVersions"] = [{"id": v["id"]} for v in original["fixVersions"]]
        if original.get("parent"):
            fields["parent"] = {"key": original["parent"]["key"]}
    return fields
