from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.transition_issue.command import TransitionIssue
from acli_py.application.ports import Workflow
from acli_py.domain.workflow import pick


@command_handler
def transition_issue(request: TransitionIssue, workflow: Workflow) -> Changed:
    """Pick the transition leading where asked, apply it, and say what the status was."""
    key = request.key.strip().upper()
    before = workflow.status(key)
    chosen = pick(workflow.transitions(key), request.to, key)
    workflow.transition(key, chosen.id, request.fields, request.comment)
    return Changed(
        key,
        before={"status": before.name if before else None},
        after={"status": chosen.target},
    )
