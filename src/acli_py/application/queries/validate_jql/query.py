from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.validate_jql.view import JqlProblems


@query
@dataclass(frozen=True)
class ValidateJql(Query[JqlProblems]):
    """The site's complaints about `jql`; none when it is valid."""

    jql: str
