"""What the interactive front ends can ask for, before these queries get packages of their own.

Queries only read, so their answers can be cached. Messages are frozen dataclasses: they are
the cache keys. Commands live in `acli_py.application.commands`, one package each.
"""

from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

# ── queries ──────────────────────────────────────────────────────────────────


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
