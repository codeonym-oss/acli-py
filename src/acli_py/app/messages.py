"""What the interactive front ends can ask for (queries) and do (commands).

Queries only read, so their answers can be cached; commands change Jira, and each successful
one announces an `IssueChanged` event, which drops the cache and tells the screens to refresh.
Messages are frozen dataclasses: they are the cache keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mediary.cqrs import Command, Query, command, event, query

LIST_FIELDS = ("summary", "status", "issuetype", "priority", "assignee", "labels", "updated")
DETAIL_FIELDS = (
    "summary", "status", "issuetype", "priority", "assignee", "reporter", "labels", "components",
    "fixVersions", "parent", "duedate", "created", "updated", "resolution", "description",
    "subtasks", "issuelinks", "comment", "watches", "project",
)  # fmt: skip


@dataclass(frozen=True)
class Page:
    """One page of search results."""

    issues: list[dict]
    next_token: str | None
    jql: str


# ── queries ──────────────────────────────────────────────────────────────────


@query
@dataclass(frozen=True)
class SearchIssues(Query[Page]):
    """One page of the issues matching a JQL query."""

    jql: str
    token: str | None = None
    size: int = 50
    fields: tuple[str, ...] = LIST_FIELDS


@query
@dataclass(frozen=True)
class CountIssues(Query[int]):
    """How many issues a JQL query matches (Jira's estimate)."""

    jql: str


@query
@dataclass(frozen=True)
class GetIssue(Query[dict]):
    """An issue with everything the detail pane shows."""

    key: str


@query
@dataclass(frozen=True)
class GetTransitions(Query[list]):
    """The transitions available on an issue now."""

    key: str


@query
@dataclass(frozen=True)
class FindAssignees(Query[list]):
    """People who can be assigned an issue, matching a name or email."""

    key: str
    text: str = ""


@query
@dataclass(frozen=True)
class ValidateJql(Query[list]):
    """Jira's errors for a query; empty when it is valid."""

    jql: str


@query
@dataclass(frozen=True)
class ListFilters(Query[list]):
    """The user's favourite filters."""


@query
@dataclass(frozen=True)
class ListPriorities(Query[list]):
    """The site's priorities."""


@query
@dataclass(frozen=True)
class ListProjects(Query[list]):
    """Projects, most recently viewed first."""


@query
@dataclass(frozen=True)
class ListIssueTypes(Query[list]):
    """The issue types a project can create."""

    project: str


# ── commands ─────────────────────────────────────────────────────────────────


@command
@dataclass(frozen=True)
class TransitionIssue(Command[str]):
    """Move an issue through a transition; returns the new status name."""

    key: str
    transition_id: str
    status: str = ""
    comment: str = ""


@command
@dataclass(frozen=True)
class AssignIssue(Command[None]):
    """Assign an issue (account_id None: unassign)."""

    key: str
    account_id: str | None
    name: str = ""


@command
@dataclass(frozen=True)
class CommentOnIssue(Command[str]):
    """Add a Markdown comment; returns the comment id."""

    key: str
    body: str


@command
@dataclass(frozen=True)
class UpdateIssue(Command[None]):
    """Set fields of an issue (summary, priority…), and add or remove labels."""

    key: str
    fields: tuple[tuple[str, object], ...] = ()
    add_labels: tuple[str, ...] = ()
    remove_labels: tuple[str, ...] = ()


@command
@dataclass(frozen=True)
class CreateIssue(Command[str]):
    """Create an issue; returns its key."""

    project: str
    issue_type: str
    summary: str
    description: str = ""
    assign_to_me: bool = False
    labels: tuple[str, ...] = ()


@command
@dataclass(frozen=True)
class WatchIssue(Command[None]):
    """Start or stop watching an issue."""

    key: str
    watch: bool = True


# ── events ───────────────────────────────────────────────────────────────────


@event
@dataclass(frozen=True)
class IssueChanged:
    """A command changed an issue (or, in a dry run, would have)."""

    key: str
    what: str
    dry_run: bool = False
    extra: dict = field(default_factory=dict, compare=False, hash=False)
