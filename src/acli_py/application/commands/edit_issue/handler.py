from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.edit_issue.command import EditIssue
from acli_py.application.ports import IssueEditor
from acli_py.domain import edits

ASSIGNEE = "assignee"


@command_handler
def edit_issue(request: EditIssue, editor: IssueEditor) -> Changed:
    """Read the fields the edit touches, apply it, and say what they held before and after."""
    key = request.key.strip().upper()
    if not request.touched:
        return Changed(key)
    before = editor.values(key, request.touched)
    fields = {f: v for f, v in request.fields.items() if f != ASSIGNEE}
    editor.edit(key, fields, request.update, notify=request.notify)
    if ASSIGNEE in request.fields:
        editor.assign(key, (request.fields[ASSIGNEE] or {}).get("accountId"))
    after = {f: edits.after(before[f], ops) for f, ops in request.update.items()}
    after.update(request.fields)
    return Changed(key, before, after)
