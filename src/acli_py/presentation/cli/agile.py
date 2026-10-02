"""`acli-py board` and `acli-py sprint`: Jira Software's boards and sprints (the Agile API)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

import typer
from rich.markup import escape

from acli_py.application.commands.close_sprint.command import CloseSprint
from acli_py.application.commands.create_board.command import BOARD_TYPES, CreateBoard
from acli_py.application.commands.create_sprint.command import CreateSprint
from acli_py.application.commands.delete_board.command import DeleteBoard
from acli_py.application.commands.delete_sprint.command import DeleteSprint
from acli_py.application.commands.move_to_sprint.command import MoveToSprint
from acli_py.application.commands.start_sprint.command import StartSprint
from acli_py.application.commands.update_sprint.command import UpdateSprint
from acli_py.application.queries.get_board.query import GetBoard
from acli_py.application.queries.get_sprint.query import GetSprint
from acli_py.application.queries.issue_columns import split
from acli_py.application.queries.list_backlog.query import ListBacklog
from acli_py.application.queries.list_board_projects.query import ListBoardProjects
from acli_py.application.queries.list_boards.query import ListBoards
from acli_py.application.queries.list_sprint_issues.query import ListSprintIssues
from acli_py.application.queries.list_sprints.query import ListSprints
from acli_py.domain.agile import SPRINT_WEEKS, SprintState
from acli_py.domain.values import when
from acli_py.presentation import output
from acli_py.presentation.cli.common import (
    AllOpt,
    BulkLimitOpt,
    ConcurrencyOpt,
    CsvOpt,
    DryRunOpt,
    FieldsOpt,
    FilterOpt,
    ForceOpt,
    FormatOpt,
    FromFileOpt,
    JqlOpt,
    JsonOpt,
    KeepGoingOpt,
    KeysArg,
    LimitOpt,
    OutputOpt,
    Session,
    WebOpt,
    YesOpt,
    connect,
    fail,
    fmt,
    guarded,
    limit_of,
    open_url,
    pick_issues,
    run_many,
    show_issues,
    template_of,
)
from acli_py.presentation.output import Column, Format

board_app = typer.Typer(help="Work with boards.", no_args_is_help=True)
sprint_app = typer.Typer(help="Plan, start and close sprints.", no_args_is_help=True)

BoardIdArg = Annotated[int, typer.Argument(help="Board id (see `acli-py board list`).")]
SprintIdArg = Annotated[int, typer.Argument(help="Sprint id (see `acli-py sprint list`).")]
BoardOpt = Annotated[
    int | None,
    typer.Option("--board", "-b", help="Board id (default: `acli-py config set board`)."),
]
StateOpt = Annotated[
    list[str] | None,
    typer.Option("--state", "-s", help="future, active or closed (repeatable)."),
]

SPRINT_COLUMNS = [
    Column("Id", lambda s: s["id"], style="cyan"),
    Column("Name", lambda s: s["name"], style="bold"),
    Column("State", lambda s: s["state"]),
    Column("Start", lambda s: when(s["startDate"], with_time=False)),
    Column("End", lambda s: when(s["endDate"], with_time=False)),
    Column("Goal", lambda s: s["goal"]),
]


def board_id(session: Session, board: int | None) -> int:
    """Return --board or the configured default board, or fail."""
    if board is not None:
        return board
    default = session.config.defaults.get("board")
    if not default:
        raise fail(
            "No board given. Pass [bold]--board ID[/] or run [bold]acli-py config set board ID[/]."
        )
    return int(default)


def moment_of(text: str | None, end_of_day: bool = False) -> datetime | None:
    """Return the moment typed: an ISO time, or a date (UTC midnight, or 23:59 at its end)."""
    if not text:
        return None
    text = text.strip()
    try:
        if "T" in text:
            moment = datetime.fromisoformat(text)
            return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
        moment = datetime.fromisoformat(text).replace(tzinfo=UTC)
    except ValueError:
        raise fail(f"{escape(text)!r} is not a date like 2026-10-05 or 2026-10-05T09:00.") from None
    return moment.replace(hour=23, minute=59) if end_of_day else moment


def _issue_list(
    session: Session,
    message: ListBacklog | ListSprintIssues,
    template: str | None,
    chosen: Format,
    *,
    empty: str,
) -> None:
    """Print the issues a board or sprint lists, like `issue search` does."""
    show_issues(session.send(message), chosen, template_of(template, chosen), empty=empty)


def _shown(fields: str | None, template: str | None, chosen: Format) -> tuple[str, ...]:
    """Return the columns to fetch: --fields, plus whatever --format names."""
    shape = template_of(template, chosen)
    return (*split(fields), *(shape.names if shape else ()))


# ── boards ───────────────────────────────────────────────────────────────────


@board_app.command("list")
@guarded
def board_list(
    name: Annotated[str | None, typer.Option("--name", "-q", help="Name contains.")] = None,
    board_type: Annotated[
        str | None, typer.Option("--type", "-t", help="scrum, kanban or simple.")
    ] = None,
    project: Annotated[
        str | None, typer.Option("--project", "-p", help="Boards about this project.")
    ] = None,
    filter_id: Annotated[
        str | None, typer.Option("--filter", help="Boards using this filter id.")
    ] = None,
    order: Annotated[
        str | None, typer.Option("--order", help="Sort by name: name, or -name for Z to A.")
    ] = None,
    private: Annotated[
        bool,
        typer.Option("--private", help="Also list private boards (Jira hides their names)."),
    ] = False,
    limit: LimitOpt = 50,
    all_pages: AllOpt = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    out: OutputOpt = None,
) -> None:
    """List boards."""
    found = connect().send(
        ListBoards(name, board_type, project, filter_id, order, private, limit_of(limit, all_pages))
    )
    output.emit(
        found.to_json(),
        [
            Column("Id", lambda b: b["id"], style="cyan"),
            Column("Name", lambda b: b["name"], style="bold"),
            Column("Type", lambda b: b["type"]),
            Column("Project", lambda b: b["projectKey"]),
        ],
        fmt(as_json, as_csv, out),
        empty="No boards found.",
    )


@board_app.command("view")
@guarded
def board_view(board: BoardIdArg, web: WebOpt = False, as_json: JsonOpt = False) -> None:
    """Show a board's details."""
    session = connect()
    if web:
        open_url(f"{session.url}/secure/RapidBoard.jspa?rapidView={board}")
        return
    found = session.send(GetBoard(board))
    if as_json:
        output.print_json(found.to_json())
        return
    setup = found.setup
    rows = [
        ("Name", escape(setup.board.name)),
        ("Type", setup.board.type),
        ("Project", escape(setup.board.location)),
        ("Filter", f"{setup.filter_id} [dim](acli-py filter view …)[/]"),
        ("Columns", escape(" → ".join(setup.columns))),
        ("Estimation", escape(setup.estimation)),
    ]
    output.console.print(output.details(f"Board {board}", rows))


@board_app.command("create")
@guarded
def board_create(
    name: Annotated[str, typer.Option("--name", help="Board name.")],
    filter_id: Annotated[int, typer.Option("--filter", help="Saved filter id that feeds it.")],
    board_type: Annotated[
        str, typer.Option("--type", "-t", help=" or ".join(BOARD_TYPES) + ".")
    ] = "kanban",
    project: Annotated[
        str | None,
        typer.Option("--project", "-p", help="Put it in this project (else your own board)."),
    ] = None,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Create a board from a saved filter."""
    command = CreateBoard(name, filter_id, board_type, project)
    session = connect(dry_run)
    run_many(
        session,
        [command],
        done="would be created" if session.dry_run else "created",
        as_json=as_json,
        describe=_new_id(session, "board"),
    )


def _new_id(session: Session, what: str) -> Any:
    """Return how a creation's line ends: the new thing's id, unless nothing was made."""
    return lambda result: "" if session.dry_run else f"[dim](id {result.after.get(what)})[/]"


@board_app.command("delete")
@guarded
def board_delete(
    boards: Annotated[list[int], typer.Argument(help="Board ids.")],
    yes: YesOpt = False,
    keep_going: KeepGoingOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Delete boards (their issues and filters stay)."""
    session = connect(dry_run)
    run_many(
        session,
        [DeleteBoard(b) for b in boards],
        done="would be deleted" if session.dry_run else "deleted",
        yes=yes,
        keep_going=keep_going,
        concurrency=1,
    )


@board_app.command("projects")
@guarded
def board_projects(
    board: BoardIdArg,
    limit: LimitOpt = 50,
    all_pages: AllOpt = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    out: OutputOpt = None,
) -> None:
    """List the projects a board shows."""
    found = connect().send(ListBoardProjects(board, limit_of(limit, all_pages)))
    output.emit(
        found.to_json(),
        [
            Column("Key", lambda p: p["key"], style="cyan"),
            Column("Name", lambda p: p["name"], style="bold"),
            Column("Id", lambda p: p["id"], style="dim"),
        ],
        fmt(as_json, as_csv, out),
    )


@board_app.command("backlog")
@guarded
def board_backlog(
    board: BoardIdArg,
    jql: JqlOpt = None,
    limit: LimitOpt = 50,
    all_pages: AllOpt = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    out: OutputOpt = None,
    fields: FieldsOpt = None,
    template: FormatOpt = None,
) -> None:
    """List the issues in a board's backlog."""
    chosen = fmt(as_json, as_csv, out)
    message = ListBacklog(board, jql, limit_of(limit, all_pages), _shown(fields, template, chosen))
    _issue_list(connect(), message, template, chosen, empty="The backlog is empty.")


# ── sprints ──────────────────────────────────────────────────────────────────


@sprint_app.command("list")
@board_app.command("sprints")
@guarded
def sprint_list(
    board: Annotated[int | None, typer.Argument(help="Board id (default: config).")] = None,
    state: StateOpt = None,
    limit: LimitOpt = 50,
    all_pages: AllOpt = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    out: OutputOpt = None,
) -> None:
    """List a board's sprints."""
    session = connect()
    try:
        states = tuple(SprintState(s.strip()) for v in state or [] for s in v.split(","))
    except ValueError as error:
        raise fail(f"{escape(str(error))}: use future, active or closed.") from None
    found = session.send(ListSprints(board_id(session, board), states, limit_of(limit, all_pages)))
    output.emit(found.to_json(), SPRINT_COLUMNS, fmt(as_json, as_csv, out), empty="No sprints.")


@sprint_app.command("view")
@guarded
def sprint_view(sprint: SprintIdArg, as_json: JsonOpt = False) -> None:
    """Show a sprint."""
    found = connect().send(GetSprint(sprint))
    if as_json:
        output.print_json(found.to_json())
        return
    data = found.sprint
    rows = [
        ("Name", escape(data.name)),
        ("State", data.state.value),
        ("Board", data.board_id),
        ("Start", when(data.start)),
        ("End", when(data.end)),
        ("Completed", when(data.completed)),
        ("Goal", escape(data.goal)),
    ]
    output.console.print(output.details(f"Sprint {sprint}", rows))


NameOpt = Annotated[str | None, typer.Option("--name", help="Sprint name.")]
StartOpt = Annotated[str | None, typer.Option("--start", help="Start: YYYY-MM-DD or ISO time.")]
EndOpt = Annotated[str | None, typer.Option("--end", help="End: YYYY-MM-DD or ISO time.")]
GoalOpt = Annotated[str | None, typer.Option("--goal", "-g", help="Sprint goal.")]


@sprint_app.command("create")
@guarded
def sprint_create(
    name: Annotated[str, typer.Option("--name", help="Sprint name.")],
    board: BoardOpt = None,
    start: StartOpt = None,
    end: EndOpt = None,
    goal: GoalOpt = None,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Create a future sprint on a board."""
    session = connect(dry_run)
    command = CreateSprint(
        board_id(session, board), name, moment_of(start), moment_of(end, end_of_day=True), goal
    )
    run_many(
        session,
        [command],
        done="would be created" if session.dry_run else "created",
        as_json=as_json,
        describe=_new_id(session, "sprint"),
    )


@sprint_app.command("update")
@guarded
def sprint_update(
    sprint: SprintIdArg,
    name: NameOpt = None,
    start: StartOpt = None,
    end: EndOpt = None,
    goal: GoalOpt = None,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Rename a sprint or change its dates or goal."""
    command = UpdateSprint(sprint, name, moment_of(start), moment_of(end, end_of_day=True), goal)
    session = connect(dry_run)
    run_many(session, [command], done="would be updated" if session.dry_run else "updated", yes=yes)


@sprint_app.command("start")
@guarded
def sprint_start(
    sprint: SprintIdArg,
    start: StartOpt = None,
    end: EndOpt = None,
    weeks: Annotated[
        int, typer.Option("--weeks", min=1, max=8, help="Length when no --end is given.")
    ] = SPRINT_WEEKS,
    goal: GoalOpt = None,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Start a future sprint (now, for --weeks, unless dates are given)."""
    command = StartSprint(sprint, moment_of(start), moment_of(end, end_of_day=True), weeks, goal)
    session = connect(dry_run)
    run_many(
        session,
        [command],
        done="would start" if session.dry_run else "started",
        yes=yes,
        describe=lambda r: f"[dim](until {when(r.after['end'], with_time=False)})[/]",
    )


@sprint_app.command("close")
@guarded
def sprint_close(sprint: SprintIdArg, yes: YesOpt = False, dry_run: DryRunOpt = False) -> None:
    """Complete an active sprint. Unfinished issues go back to the backlog."""
    session = connect(dry_run)
    run_many(
        session,
        [CloseSprint(sprint)],
        done="would be closed" if session.dry_run else "closed",
        yes=yes,
    )


@sprint_app.command("delete")
@guarded
def sprint_delete(
    sprints: Annotated[list[int], typer.Argument(help="Sprint ids.")],
    yes: YesOpt = False,
    keep_going: KeepGoingOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Delete sprints; their issues move to the backlog."""
    session = connect(dry_run)
    run_many(
        session,
        [DeleteSprint(s) for s in sprints],
        done="would be deleted" if session.dry_run else "deleted",
        yes=yes,
        keep_going=keep_going,
        concurrency=1,
    )


@sprint_app.command("issues")
@guarded
def sprint_issues(
    sprint: SprintIdArg,
    jql: JqlOpt = None,
    fields: FieldsOpt = None,
    template: FormatOpt = None,
    limit: LimitOpt = 50,
    all_pages: AllOpt = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    out: OutputOpt = None,
) -> None:
    """List the issues in a sprint."""
    chosen = fmt(as_json, as_csv, out)
    shown = _shown(fields, template, chosen)
    message = ListSprintIssues(sprint, jql, limit_of(limit, all_pages), shown)
    _issue_list(connect(), message, template, chosen, empty="No issues.")


def _move(
    session: Session,
    sprint: int | None,
    picked: list[str],
    *,
    yes: bool,
    concurrency: int,
    keep_going: bool,
    force: bool,
    as_json: bool,
) -> None:
    """Move the issues into the sprint (None: the backlog), asking once."""
    if not picked:
        output.info("No issues match; nothing to move.")
        return
    where = f"into sprint {sprint}" if sprint else "to the backlog"
    run_many(
        session,
        [MoveToSprint(key, sprint) for key in picked],
        done=f"would move {where}" if session.dry_run else f"moved {where}",
        yes=yes,
        concurrency=concurrency,
        keep_going=keep_going,
        force=force,
        as_json=as_json,
    )


@sprint_app.command("add")
@guarded
def sprint_add(
    sprint: SprintIdArg,
    keys: KeysArg = None,
    jql: JqlOpt = None,
    saved_filter: FilterOpt = None,
    from_file: FromFileOpt = None,
    limit: BulkLimitOpt = None,
    concurrency: ConcurrencyOpt = 4,
    keep_going: KeepGoingOpt = False,
    force: ForceOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Move issues into a sprint.

    [dim]acli-py sprint add 8 DEMO-1 DEMO-2
    acli-py issue search 'p:DEMO is:open #web' --output keys | acli-py sprint add 8 -[/]
    """
    session = connect(dry_run)
    picked = pick_issues(session, keys, jql, saved_filter, from_file, limit=limit, force=force)
    _move(
        session,
        sprint,
        picked,
        yes=yes,
        concurrency=concurrency,
        keep_going=keep_going,
        force=force,
        as_json=as_json,
    )


@sprint_app.command("remove")
@guarded
def sprint_remove(
    keys: KeysArg = None,
    jql: JqlOpt = None,
    saved_filter: FilterOpt = None,
    from_file: FromFileOpt = None,
    limit: BulkLimitOpt = None,
    concurrency: ConcurrencyOpt = 4,
    keep_going: KeepGoingOpt = False,
    force: ForceOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Move issues out of their sprint, back to the backlog."""
    session = connect(dry_run)
    picked = pick_issues(session, keys, jql, saved_filter, from_file, limit=limit, force=force)
    _move(
        session,
        None,
        picked,
        yes=yes,
        concurrency=concurrency,
        keep_going=keep_going,
        force=force,
        as_json=as_json,
    )
