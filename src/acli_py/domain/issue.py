"""An issue as plain Python: what Jira's JSON means, parsed once at the edge.

`Issue.from_jira` reads the JSON of `GET /issue/{key}`; everything past it works with these
frozen objects instead of digging through nested dicts. Missing or null parts become empty
values (None, "", ()), never errors: Jira leaves out whatever a screen or a permission hides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from acli_py.domain import adf
from acli_py.domain.values import day, moment

if TYPE_CHECKING:
    from datetime import date, datetime

# The fields `Issue` reads itself; any other field it is given lands in `Issue.other`.
KNOWN_FIELDS = frozenset({
    "summary", "status", "issuetype", "priority", "assignee", "reporter", "labels", "components",
    "fixVersions", "parent", "duedate", "created", "updated", "resolution", "description",
    "subtasks", "issuelinks", "comment", "attachment", "watches", "project",
})  # fmt: skip


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _names(values: Any) -> tuple[str, ...]:
    return tuple(str(v["name"]) for v in values or () if isinstance(v, dict) and v.get("name"))


class StatusCategory(StrEnum):
    """Where a status sits in every workflow: Jira's three columns."""

    TO_DO = "new"
    IN_PROGRESS = "indeterminate"
    DONE = "done"
    UNKNOWN = "undefined"


@dataclass(frozen=True)
class Status:
    """A workflow status, such as 'In Review', and its category."""

    name: str
    category: StatusCategory = StatusCategory.UNKNOWN

    @classmethod
    def from_jira(cls, data: Any) -> Status | None:
        """Return the status in `data`, or None."""
        if not isinstance(data, dict) or not data.get("name"):
            return None
        key = _dict(data.get("statusCategory")).get("key")
        try:
            category = StatusCategory(key)
        except ValueError:
            category = StatusCategory.UNKNOWN
        return cls(str(data["name"]), category)


@dataclass(frozen=True)
class User:
    """A person, as far as Jira lets us see them."""

    account_id: str
    name: str
    email: str = ""

    @classmethod
    def from_jira(cls, data: Any) -> User | None:
        """Return the user in `data`, or None."""
        if not isinstance(data, dict) or not (data.get("accountId") or data.get("displayName")):
            return None
        return cls(
            str(data.get("accountId") or ""),
            str(data.get("displayName") or data.get("accountId")),
            str(data.get("emailAddress") or ""),
        )


@dataclass(frozen=True)
class IssueType:
    """What kind of work an issue is: a Bug, a Story, a Sub-task."""

    name: str
    subtask: bool = False

    @classmethod
    def from_jira(cls, data: Any) -> IssueType | None:
        """Return the issue type in `data`, or None."""
        if not isinstance(data, dict) or not data.get("name"):
            return None
        return cls(str(data["name"]), bool(data.get("subtask")))


@dataclass(frozen=True)
class IssueRef:
    """Another issue, as an issue mentions it: its parent, a subtask, a linked issue."""

    key: str
    summary: str = ""
    status: Status | None = None

    @classmethod
    def from_jira(cls, data: Any) -> IssueRef | None:
        """Return the reference in `data`, or None."""
        if not isinstance(data, dict) or not data.get("key"):
            return None
        fields = _dict(data.get("fields"))
        summary, status = str(fields.get("summary") or ""), Status.from_jira(fields.get("status"))
        return cls(str(data["key"]), summary, status)


class Direction(StrEnum):
    """Which end of a link an issue is on."""

    OUTWARD = "outward"  # this issue <phrase> the other: DEMO-1 blocks DEMO-3
    INWARD = "inward"  # the other <phrase> this issue: DEMO-3 is blocked by DEMO-1


@dataclass(frozen=True)
class Link:
    """A link from this issue to another, read from this issue's side."""

    id: str
    type: str
    phrase: str
    direction: Direction
    issue: IssueRef

    @classmethod
    def from_jira(cls, data: Any) -> Link | None:
        """Return the link in `data`, or None."""
        if not isinstance(data, dict):
            return None
        kind = _dict(data.get("type"))
        if "outwardIssue" in data:
            direction, phrase, other = Direction.OUTWARD, kind.get("outward"), data["outwardIssue"]
        else:
            direction, phrase, other = Direction.INWARD, kind.get("inward"), data.get("inwardIssue")
        issue = IssueRef.from_jira(other)
        if issue is None:
            return None
        return cls(
            str(data.get("id") or ""),
            str(kind.get("name") or ""),
            str(phrase or "relates to"),
            direction,
            issue,
        )


@dataclass(frozen=True)
class Comment:
    """A comment, its body as Markdown."""

    id: str
    author: User | None
    created: datetime | None
    body: str

    @classmethod
    def from_jira(cls, data: Any) -> Comment:
        """Return the comment in `data`."""
        data = _dict(data)
        return cls(
            str(data.get("id") or ""),
            User.from_jira(data.get("author")),
            moment(data.get("created")),
            adf.to_text(data.get("body")).strip(),
        )


@dataclass(frozen=True)
class Attachment:
    """A file attached to an issue."""

    id: str
    filename: str
    size: int = 0

    @classmethod
    def from_jira(cls, data: Any) -> Attachment:
        """Return the attachment in `data`."""
        data = _dict(data)
        filename = str(data.get("filename") or "?")
        return cls(str(data.get("id") or ""), filename, int(data.get("size") or 0))


@dataclass(frozen=True)
class Field:
    """A field `Issue` doesn't model itself (custom fields, mostly), with its raw value."""

    id: str
    name: str
    value: Any = field(compare=False)


@dataclass(frozen=True)
class Issue:
    """One issue, with everything a detail view shows."""

    key: str
    summary: str = ""
    id: str = ""
    project: str = ""
    type: IssueType | None = None
    status: Status | None = None
    priority: str = ""
    resolution: str = ""
    assignee: User | None = None
    reporter: User | None = None
    labels: tuple[str, ...] = ()
    components: tuple[str, ...] = ()
    fix_versions: tuple[str, ...] = ()
    parent: IssueRef | None = None
    due: date | None = None
    created: datetime | None = None
    updated: datetime | None = None
    description: str = ""
    subtasks: tuple[IssueRef, ...] = ()
    links: tuple[Link, ...] = ()
    comments: tuple[Comment, ...] = ()
    comment_count: int = 0
    attachments: tuple[Attachment, ...] = ()
    watchers: int = 0
    watching: bool = False
    other: tuple[Field, ...] = ()

    @classmethod
    def from_jira(cls, data: dict) -> Issue:
        """Return the issue in Jira's JSON (with `names` when fetched with expand=names)."""
        f = _dict(data.get("fields"))
        names = _dict(data.get("names"))
        comment = _dict(f.get("comment"))
        comments = tuple(Comment.from_jira(c) for c in comment.get("comments") or ())
        watches = _dict(f.get("watches"))
        return cls(
            key=str(data["key"]),
            id=str(data.get("id") or ""),
            summary=str(f.get("summary") or ""),
            project=str(_dict(f.get("project")).get("key") or ""),
            type=IssueType.from_jira(f.get("issuetype")),
            status=Status.from_jira(f.get("status")),
            priority=str(_dict(f.get("priority")).get("name") or ""),
            resolution=str(_dict(f.get("resolution")).get("name") or ""),
            assignee=User.from_jira(f.get("assignee")),
            reporter=User.from_jira(f.get("reporter")),
            labels=tuple(str(label) for label in f.get("labels") or ()),
            components=_names(f.get("components")),
            fix_versions=_names(f.get("fixVersions")),
            parent=IssueRef.from_jira(f.get("parent")),
            due=day(f.get("duedate")),
            created=moment(f.get("created")),
            updated=moment(f.get("updated")),
            description=adf.to_text(f.get("description")).strip(),
            subtasks=tuple(r for r in map(IssueRef.from_jira, f.get("subtasks") or ()) if r),
            links=tuple(link for link in map(Link.from_jira, f.get("issuelinks") or ()) if link),
            comments=comments,
            comment_count=int(comment.get("total") or len(comments)),
            attachments=tuple(Attachment.from_jira(a) for a in f.get("attachment") or ()),
            watchers=int(watches.get("watchCount") or 0),
            watching=bool(watches.get("isWatching")),
            other=tuple(
                Field(field_id, str(names.get(field_id) or field_id), value)
                for field_id, value in sorted(f.items())
                if field_id not in KNOWN_FIELDS and value not in (None, "", [], {})
            ),
        )
