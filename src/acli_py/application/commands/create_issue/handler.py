from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.create_issue.command import CreateIssue
from acli_py.application.ports import IssueStore
from acli_py.domain.values import text


@command_handler
def create_issue(request: CreateIssue, store: IssueStore) -> Changed:
    """Create the issue; `Changed` names it, with nothing before (undoing it deletes it)."""
    key = store.create(request.fields, request.update)
    project = text(request.fields.get("project")) or key.rpartition("-")[0]
    return Changed(key, after={"created": key, "project": project, "summary": request.summary})
