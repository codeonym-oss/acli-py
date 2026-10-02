from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mediary.cqrs import query_handler

from acli_py.application.commands.create_issue.command import CreateIssue
from acli_py.application.commands.edit_issue.command import EditIssue
from acli_py.application.ports import IssueEditor, IssueFields
from acli_py.application.queries.plan_import.query import PlanImport
from acli_py.application.queries.plan_import.view import (
    MATCHED,
    READ_ONLY,
    ImportPlan,
    ImportStep,
)
from acli_py.domain import edits
from acli_py.domain.values import text

KEY_COLUMNS = ("key", "issuekey")
# Columns a list or an export carries that no edit can set: a transition sets them.
READ_ONLY_COLUMNS = ("status", "created", "updated", "resolution", "id")
# Fields only a new issue takes: moving or retyping an issue is not an edit.
CREATE_ONLY = ("project", "issuetype")


@query_handler
def plan_import(request: PlanImport, fields: IssueFields, editor: IssueEditor) -> ImportPlan:
    """Map the columns, then plan a command per row that changes something."""
    mapping = _mapping(request.rows, fields)
    steps: list[ImportStep] = []
    unchanged: list[str] = []
    problems: list[tuple[str, str]] = []
    for number, row in enumerate(request.rows, 1):
        key = next((str(row[c]).strip().upper() for c in row if _is_key(c) and row[c]), "")
        ref = key or f"#{number}"
        given = {c: _plain(v) for c, v in row.items() if mapping[c] not in (MATCHED, READ_ONLY)}
        try:
            step = (
                _update(key, given, mapping, fields, editor)
                if key
                else _create(ref, given, request, fields)
            )
        except ValueError as error:
            problems.append((ref, str(error)))
            continue
        if step is None:
            unchanged.append(key)
        else:
            steps.append(step)
    return ImportPlan(tuple(mapping.items()), tuple(steps), tuple(unchanged), tuple(problems))


def _mapping(rows: tuple[Mapping[str, Any], ...], fields: IssueFields) -> dict[str, str]:
    """Return the field each column fills; refuse columns that fill none."""
    mapping: dict[str, str] = {}
    unknown = []
    for column in dict.fromkeys(c for row in rows for c in row):
        if _is_key(column):
            mapping[column] = MATCHED
        elif column.strip().lower() in READ_ONLY_COLUMNS:
            mapping[column] = READ_ONLY
        else:
            try:
                mapping[column] = fields.field_of(column)
            except ValueError:
                unknown.append(column)
    if unknown:
        raise ValueError(
            f"No field is called {', '.join(repr(c) for c in unknown)}: rename or drop "
            "those columns (acli-py field list shows the names)."
        )
    return mapping


def _update(
    key: str,
    given: dict[str, Any],
    mapping: Mapping[str, str],
    fields: IssueFields,
    editor: IssueEditor,
) -> ImportStep | None:
    """Plan the edit of what differs between the row and the issue now (None: nothing)."""
    settable = {c: v for c, v in given.items() if mapping[c] not in CREATE_ONLY}
    wanted = fields.build(settable) if settable else {}
    try:
        now = editor.values(key, (*wanted, "summary"))
    except Exception as error:  # the site's own error (not found, no permission): one row
        raise ValueError(str(error)) from error
    changed = {f: v for f, v in wanted.items() if not edits.equal(now.get(f), v)}
    if not changed:
        return None
    return ImportStep(
        key,
        text(now.get("summary")),
        EditIssue(key, changed),
        ", ".join(f"{f}: {text(now.get(f)) or 'none'}" for f in changed),
        ", ".join(f"{f}: {text(v) or 'none'}" for f, v in changed.items()),
    )


def _create(
    ref: str, given: dict[str, Any], request: PlanImport, fields: IssueFields
) -> ImportStep:
    """Plan a new issue from the row, in the project and of the type it (or the import) says."""
    row = {"project": request.project, "type": request.issue_type, **given}
    if not row.get("project"):
        raise ValueError("no project: add a project column, or give one with --project")
    wanted = fields.build(row, creating=True)
    project, kind = text(wanted.get("project")), text(wanted.get("issuetype"))
    summary = str(wanted.get("summary") or "")
    return ImportStep(
        ref, summary, CreateIssue(wanted, ref=ref), "", f"new {kind} in {project}", creates=True
    )


def _is_key(column: str) -> bool:
    return column.strip().lower() in KEY_COLUMNS


def _plain(value: Any) -> Any:
    """Return a value as typed: people, issues and options from JSON by their id or name."""
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, Mapping):
        for name in ("accountId", "key", "name", "value", "id"):
            if value.get(name) not in (None, ""):
                return value[name]
        return None
    return value
