from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.delete_issue.command import DeleteIssue
from acli_py.application.ports import IssueEditor, IssueStore

# What the audit log keeps of a deleted issue, so it says what was lost.
NOTED = ("summary", "issuetype", "status")


@command_handler
def delete_issue(request: DeleteIssue, editor: IssueEditor, store: IssueStore) -> Changed:
    """Delete the issue, keeping its summary, type and status in `Changed.before`."""
    key = request.key.strip().upper()
    before = editor.values(key, NOTED)
    store.delete(key, subtasks=request.subtasks)
    return Changed(key, before=before, after={"deleted": True})
