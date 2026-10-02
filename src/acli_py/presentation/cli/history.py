"""`acli-py log` and `acli-py undo`: the changes the audit log keeps, and reversing them."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.markup import escape

from acli_py.application.queries.list_changes.query import ListChanges
from acli_py.application.queries.plan_undo.query import PlanUndo
from acli_py.domain.values import when
from acli_py.presentation import output
from acli_py.presentation.cli.common import (
    AllOpt,
    ConcurrencyOpt,
    CsvOpt,
    DryRunOpt,
    JsonOpt,
    KeepGoingOpt,
    LimitOpt,
    OutputOpt,
    YesOpt,
    connect,
    fmt,
    guarded,
    limit_of,
    plural,
    run_many,
)
from acli_py.presentation.output import Column

SHOWN_KEYS = 4


def _undo_note(entry: dict) -> str:
    """Return how a record relates to undo: 'undone by 14', 'undoes 12', or nothing."""
    if entry["undoneBy"]:
        return f"undone by {entry['undoneBy']}"
    return f"undoes {entry['undoes']}" if entry["undoes"] else ""


def _keys(keys: list[str]) -> str:
    shown = ", ".join(keys[:SHOWN_KEYS])
    return shown + (f" +{len(keys) - SHOWN_KEYS}" if len(keys) > SHOWN_KEYS else "")


@guarded
def log(
    limit: LimitOpt = 20,
    all_pages: AllOpt = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    out: OutputOpt = None,
) -> None:
    """List the changes you made, newest first, with the ids `acli-py undo` takes.

    Every command and bulk run that changed Jira is kept in the audit log (dry runs aren't).

    [dim]acli-py log
    acli-py undo 12[/]
    """
    found = connect().send(ListChanges(limit_of(limit, all_pages)))
    output.emit(
        found.to_json(),
        [
            Column("Id", lambda e: e["id"], style="cyan", justify="right"),
            Column("When", lambda e: when(e["at"])),
            Column("Command", lambda e: e["command"], style="bold"),
            Column("Issues", lambda e: _keys(e["keys"])),
            Column("Failed", lambda e: len(e["failed"]) or "", style="red"),
            Column("Undo", _undo_note, style="dim"),
        ],
        fmt(as_json, as_csv, out),
        empty="No changes recorded yet.",
    )


@guarded
def undo(
    entry_id: Annotated[
        str | None,
        typer.Argument(help="The change to reverse (see `acli-py log`); default: the last one."),
    ] = None,
    concurrency: ConcurrencyOpt = 4,
    keep_going: KeepGoingOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Reverse a change: put back the fields, assignees and statuses it replaced.

    Shows each issue now and after, flags those changed again since, then asks once. A
    transition is undone by moving back, when the workflow allows it. The undo is itself
    recorded, so a second `undo` reverses the change before. Exits 0 when everything was put
    back, 1 when some issues couldn't be, 2 when nothing ran.

    [dim]acli-py undo
    acli-py undo 12 --dry-run[/]
    """
    session = connect(dry_run)
    plan = session.send(PlanUndo(entry_id))
    for key, why in plan.skipped:
        output.warn(f"{escape(key)}: not undone, {escape(why)}.")
    if not plan.steps:
        output.info(f"Nothing to put back for change {plan.entry.id}.")
        raise typer.Exit(1 if plan.skipped else 0)
    if plan.drifted:
        them = "it" if len(plan.drifted) == 1 else "them"
        output.warn(
            f"{escape(', '.join(plan.drifted))} changed again since change {plan.entry.id}; "
            f"undoing sets {them} back anyway."
        )
    run_many(
        session,
        plan.commands,
        done="would be put back" if session.dry_run else "put back",
        yes=yes,
        concurrency=concurrency,
        keep_going=keep_going,
        as_json=as_json,
        change=plan.change(),
        undoes=plan.entry.id,
    )
    if plan.skipped:
        output.info(f"{plural(len(plan.skipped), 'issue')} not undone.")
        raise typer.Exit(1)
