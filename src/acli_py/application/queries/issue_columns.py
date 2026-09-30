"""The columns an issue list can show, and `--format` templates over them.

A column has the name users write (`status`, `assignee`, `customfield_10016`), the Jira field
it needs, a header, and two readings of an issue: short text (tables, CSV, templates) and JSON.
Names are read in any case, with Jira's own ids as aliases (`issuetype`, `duedate`); any other
name is taken as a field id and shows that field's value as Jira sent it.
"""

from __future__ import annotations

import string
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from acli_py.application.queries.shapes import iso, ref_json, status_json, user_json
from acli_py.domain.values import text, when

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from acli_py.domain.issue import Issue


@dataclass(frozen=True)
class IssueColumn:
    """One column of an issue list."""

    name: str
    jira: str  # the field to fetch; "" when every issue has it (the key)
    header: str
    text: Callable[[Issue], str]
    json: Callable[[Issue], Any]


def _names(values: Iterable[str]) -> str:
    return ", ".join(values)


def _known() -> tuple[IssueColumn, ...]:
    C = IssueColumn  # noqa: N806
    return (
        C("key", "", "Key", lambda i: i.key, lambda i: i.key),
        C("type", "issuetype", "Type", lambda i: i.type.name if i.type else "",
          lambda i: i.type.name if i.type else None),
        C("status", "status", "Status", lambda i: i.status.name if i.status else "",
          lambda i: status_json(i.status)),
        C("priority", "priority", "Priority", lambda i: i.priority, lambda i: i.priority or None),
        C("assignee", "assignee", "Assignee", lambda i: i.assignee.name if i.assignee else "",
          lambda i: user_json(i.assignee)),
        C("reporter", "reporter", "Reporter", lambda i: i.reporter.name if i.reporter else "",
          lambda i: user_json(i.reporter)),
        C("summary", "summary", "Summary", lambda i: i.summary, lambda i: i.summary),
        C("labels", "labels", "Labels", lambda i: _names(i.labels), lambda i: list(i.labels)),
        C("components", "components", "Components", lambda i: _names(i.components),
          lambda i: list(i.components)),
        C("fixVersions", "fixVersions", "Fix versions", lambda i: _names(i.fix_versions),
          lambda i: list(i.fix_versions)),
        C("parent", "parent", "Parent", lambda i: i.parent.key if i.parent else "",
          lambda i: ref_json(i.parent)),
        C("due", "duedate", "Due", lambda i: iso(i.due) or "", lambda i: iso(i.due)),
        C("created", "created", "Created", lambda i: when(i.created), lambda i: iso(i.created)),
        C("updated", "updated", "Updated", lambda i: when(i.updated), lambda i: iso(i.updated)),
        C("resolution", "resolution", "Resolution", lambda i: i.resolution,
          lambda i: i.resolution or None),
        C("project", "project", "Project", lambda i: i.project, lambda i: i.project or None),
        C("description", "description", "Description", lambda i: " ".join(i.description.split()),
          lambda i: i.description),
    )  # fmt: skip


KNOWN = {c.name.lower(): c for c in _known()}
ALIASES = {"issuekey": "key", "issuetype": "type", "duedate": "due"}
DEFAULT = ("key", "type", "status", "priority", "assignee", "summary")


def column(name: str) -> IssueColumn:
    """Return the column called `name`: a known one (any case), else field `name` as sent."""
    wanted = name.strip()
    lowered = ALIASES.get(wanted.lower(), wanted.lower())
    if lowered in KNOWN:
        return KNOWN[lowered]
    return IssueColumn(
        wanted, wanted, wanted, lambda i: text(i.value(wanted)), lambda i: i.value(wanted)
    )


def columns(names: Iterable[str] = ()) -> tuple[IssueColumn, ...]:
    """Return the columns `names` asks for, the key always first; the defaults for none."""
    picked = [column(n) for n in names if n.strip()] or [column(n) for n in DEFAULT]
    unique = {c.name: c for c in picked if c.name != "key"}
    return (KNOWN["key"], *unique.values())


def split(names: str | None) -> tuple[str, ...]:
    """Return the names in 'key,status, summary'."""
    return tuple(n.strip() for n in (names or "").split(",") if n.strip())


def jira_fields(cols: Iterable[IssueColumn]) -> tuple[str, ...]:
    """Return the Jira fields the columns need, each once."""
    return tuple(dict.fromkeys(c.jira for c in cols if c.jira))


class Template:
    r"""A `--format` template: '{key} {status} {summary}', one line per issue.

    Each `{name}` is a column (so `{customfield_10016}` works too) and takes Python's format
    spec: `{key:<10}`. `\t` and `\n` are a tab and a newline; `{{` is a brace.
    """

    def __init__(self, source: str) -> None:
        self.source = source.replace("\\t", "\t").replace("\\n", "\n")
        try:
            parts = list(string.Formatter().parse(self.source))
        except ValueError as error:
            raise ValueError(f"bad format {source!r}: {error}") from None
        spelled = [name for _, name, _, _ in parts if name is not None]
        for name in spelled:
            if not name or name.isdigit() or any(c in name for c in ".[!"):
                raise ValueError(f"name a field in each {{}} of the format {source!r}")
        # Each name as the template spells it ('Status'), and the column it means.
        self.fields = {name: column(name) for name in spelled}

    @property
    def names(self) -> tuple[str, ...]:
        """Return the columns the template uses."""
        return tuple(dict.fromkeys(c.name for c in self.fields.values()))

    def render(self, issue: Issue) -> str:
        """Return the template filled in for `issue`."""
        return self.source.format_map({n: c.text(issue) for n, c in self.fields.items()})
