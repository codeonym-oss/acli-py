from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import IssueReader
from acli_py.application.queries.name_for_git.query import NameForGit
from acli_py.application.queries.name_for_git.view import GitNames
from acli_py.domain.helpers import branch_name, commit_message


@query_handler
def name_for_git(request: NameForGit, issues: IssueReader) -> GitNames:
    """Read the issue's type and summary, and name it."""
    issue = issues.get_issue(request.key.strip().upper())
    return GitNames(issue.key, branch_name(issue, request.prefix), commit_message(issue))
