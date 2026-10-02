from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.assign_issue.command import DEFAULT, AssignIssue
from acli_py.application.ports import IssueEditor


@command_handler
def assign_issue(request: AssignIssue, editor: IssueEditor) -> Changed:
    """Assign the issue, and say who had it before (as an account id, None for nobody)."""
    key = request.key.strip().upper()
    before = editor.values(key, ("assignee",))["assignee"] or {}
    editor.assign(key, request.account_id)
    after = request.account_id
    if after == DEFAULT:  # the project's default assignee: read back who that is
        after = (editor.values(key, ("assignee",))["assignee"] or {}).get("accountId")
    return Changed(key, before={"assignee": before.get("accountId")}, after={"assignee": after})
