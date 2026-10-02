from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import IssueSearch
from acli_py.application.queries.validate_jql.query import ValidateJql
from acli_py.application.queries.validate_jql.view import JqlProblems


@query_handler
def validate_jql(request: ValidateJql, search: IssueSearch) -> JqlProblems:
    """Ask the site."""
    return JqlProblems(tuple(search.problems(request.jql)))
