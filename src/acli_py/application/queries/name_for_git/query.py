from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.name_for_git.view import GitNames


@query
@dataclass(frozen=True)
class NameForGit(Query[GitNames]):
    """A branch and a commit message for issue `key`; `prefix` replaces 'fix' or 'feat'."""

    key: str
    prefix: str | None = None
