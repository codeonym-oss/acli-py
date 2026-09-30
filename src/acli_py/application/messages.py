"""What the interactive front ends can ask for (queries) and do (commands).

Queries only read, so their answers can be cached; commands change Jira, and each successful
one announces an `IssueChanged` event (`events/issue_changed/`), which drops the cache and
tells the screens to refresh.
Messages are frozen dataclasses: they are the cache keys.
"""

from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, Query, command, query

LIST_FIELDS = ("summary", "status", "issuetype", "priority", "assignee", "labels", "updated")


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
class CommentOnIssue(Command[str]):
    """Add a Markdown comment; returns the comment id."""

    key: str
    body: str
