from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

# Words for no one (unassigned) and for the project's default assignee.
NOBODY = ("none", "unassigned", "nobody", "-")
DEFAULT = "default"
PROJECT_DEFAULT = "-1"  # Jira's account id for "the project's default assignee"


@query
@dataclass(frozen=True)
class FindPerson(Query[str | None]):
    """The account id of `who`: '@me', an email, a name or an id.

    With `assignee`, 'none' (or 'unassigned') is None and 'default' is `PROJECT_DEFAULT`.
    """

    who: str
    assignee: bool = False
