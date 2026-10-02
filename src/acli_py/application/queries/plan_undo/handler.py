from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mediary.cqrs import query_handler

from acli_py.application.changes import AuditRecord, Changed
from acli_py.application.commands.assign_issue.command import AssignIssue
from acli_py.application.commands.edit_issue.command import EditIssue
from acli_py.application.commands.transition_issue.command import TransitionIssue
from acli_py.application.ports import AuditLog, IssueEditor, Workflow
from acli_py.application.queries.plan_undo.query import PlanUndo
from acli_py.application.queries.plan_undo.view import UndoPlan, UndoStep
from acli_py.domain import edits
from acli_py.domain.values import text
from acli_py.domain.workflow import NoSuchTransitionError, pick

# Records whose changes are field edits, put back by setting the fields as they were.
EDITS = ("EditIssue", "ImportIssues")
UNDOABLE = (*EDITS, "AssignIssue", "TransitionIssue")


@query_handler
def plan_undo(
    request: PlanUndo, audit: AuditLog, editor: IssueEditor, workflow: Workflow
) -> UndoPlan:
    """Find the record, and plan one command per issue it changed."""
    entry = _entry(audit.entries(), request.entry_id)
    if entry.command not in UNDOABLE:
        raise ValueError(
            f"Change {entry.id} ({entry.command}) can't be undone: undo puts back field "
            "edits, assignments and transitions."
        )
    steps: list[UndoStep] = []
    skipped: list[tuple[str, str]] = []
    for changed in entry.changes:
        if not changed.before:
            skipped.append((changed.key, "it was created; delete it to undo that"))
            continue
        if entry.command == "TransitionIssue":
            planned = _transition_back(changed, editor, workflow)
        else:
            planned = _put_back(changed, editor, assign=entry.command == "AssignIssue")
        if isinstance(planned, str):
            skipped.append((changed.key, planned))
        else:
            steps.append(planned)
    return UndoPlan(entry, tuple(steps), tuple(skipped))


def _entry(entries: list[AuditRecord], wanted: str | None) -> AuditRecord:
    """Return the record asked for, or the last one neither undone nor an undo itself."""
    undone = {e.undoes: e.id for e in entries if e.undoes}
    if wanted is None:
        for entry in reversed(entries):
            if entry.id not in undone and not entry.undoes:
                return entry
        raise ValueError("Nothing to undo: the log has no change left to reverse.")
    wanted = wanted.strip().lstrip("#")
    entry = next((e for e in entries if e.id == wanted), None)
    if entry is None:
        raise ValueError(f"No change {wanted} in the log. See acli-py log.")
    if wanted in undone:
        raise ValueError(f"Change {wanted} was undone already, by change {undone[wanted]}.")
    return entry


def _put_back(changed: Changed, editor: IssueEditor, *, assign: bool) -> UndoStep | str:
    """Return the edit (or assignment) that sets the fields back, or why there is none."""
    field_ids = tuple(changed.before)
    now = editor.values(changed.key, (*field_ids, "summary"))
    if all(edits.equal(now.get(f), changed.before[f]) for f in field_ids):
        return "it is as it was already"
    if assign:
        command: AssignIssue | EditIssue = AssignIssue(changed.key, changed.before["assignee"])
    else:
        command = EditIssue(changed.key, {f: edits.as_input(changed.before[f]) for f in field_ids})
    return UndoStep(
        changed.key,
        text(now.get("summary")),
        command,
        _values(field_ids, now),
        _values(field_ids, changed.before),
        drifted=any(not edits.equal(now.get(f), changed.after.get(f)) for f in changed.after),
    )


def _transition_back(changed: Changed, editor: IssueEditor, workflow: Workflow) -> UndoStep | str:
    """Return the transition back to the status the issue had, or why there is none."""
    status = str(changed.before.get("status") or "")
    now = editor.values(changed.key, ("status", "summary"))
    if edits.equal(now.get("status"), status):
        return f"it is in {status} already"
    try:
        pick(workflow.transitions(changed.key), status, changed.key)
    except NoSuchTransitionError:
        return f"no transition leads back to {status} from {text(now.get('status'))}"
    return UndoStep(
        changed.key,
        text(now.get("summary")),
        TransitionIssue(changed.key, status),
        text(now.get("status")),
        status,
        drifted=not edits.equal(now.get("status"), changed.after.get("status")),
    )


def _values(field_ids: tuple[str, ...], values: Mapping[str, Any]) -> str:
    """Return fields' values as short text: the value alone, or 'field: value, …'."""
    if len(field_ids) == 1:
        return text(values.get(field_ids[0])) or "none"
    return ", ".join(f"{f}: {text(values.get(f)) or 'none'}" for f in field_ids)
