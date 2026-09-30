from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query


@query
@dataclass(frozen=True)
class CountIssues(Query[int]):
    """How many issues `jql` matches (Jira's estimate)."""

    jql: str
