"""`acli-py board` and `acli-py sprint`: Jira Software's boards and sprints (the Agile API)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import typer
from rich.markup import escape

from acli_py.application.queries.issue_columns import columns, jira_fields, split
from acli_py.application.queries.search_issues.view import IssuesView
from acli_py.domain.issue import Issue
from acli_py.infrastructure.jira import resolve
from acli_py.infrastructure.jira.client import AGILE
from acli_py.infrastructure.jira.fields import when
from acli_py.presentation import output
from acli_py.presentation.cli.common import (
    AllOpt,
    CsvOpt,
    DryRunOpt,
    FieldsOpt,
    FormatOpt,
    IgnoreErrorsOpt,
    JqlOpt,
    JsonOpt,
    KeysArg,
    LimitOpt,
    OutputOpt,
    Session,
    WebOpt,
    YesOpt,
    confirm,
    connect,
    fail,
    fmt,
    guarded,
    limit_of,
    open_url,
    run_bulk,
    show_issues,
    template_of,
)
from acli_py.presentation.output import Column, Format, dig

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
    Column("Id", lambda s: s.get("id"), style="cyan"),
    Column("Name", lambda s: s.get("name"), style="bold"),
    Column("State", lambda s: s.get("state")),
    Column("Start", lambda s: when(s.get("startDate"), with_time=False)),
    Column("End", lambda s: when(s.get("endDate"), with_time=False)),
    Column("Goal", lambda s: s.get("goal")),
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


def iso_date(text: str | None, end_of_day: bool = False) -> str | None:
    """Return an ISO 8601 timestamp for YYYY-MM-DD or a full timestamp."""
    if not text:
        return None
    text = text.strip()
    if "T" in text:
        return text
    moment = datetime.fromisoformat(text).replace(tzinfo=UTC)
    if end_of_day:
        moment = moment.replace(hour=23, minute=59)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _issue_list(
    path: str,
    jql: str | None,
    limit: int | None,
    fields: str | None,
    template: str | None,
    chosen: Format,
    *,
    empty: str,
) -> None:
    """Print the issues an agile resource lists, like `issue search` does."""
    shape = template_of(template, chosen)
    shown = columns((*split(fields), *(shape.names if shape else ())))
    session = connect()
    found = session.client.paged(
        path, key="issues", limit=limit, jql=jql, fields=",".join(jira_fields(shown))
    )
    view = IssuesView(jql or "", tuple(Issue.from_jira(i) for i in found), shown)
    show_issues(view, chosen, shape, empty=empty)


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
    session = connect()
    boards = session.client.paged(
        f"{AGILE}/board",
        limit=limit_of(limit, all_pages),
        name=name,
        type=board_type,
        projectKeyOrId=project.upper() if project else None,
        filterId=filter_id,
        orderBy=order,
        includePrivate="true" if private else None,
    )
    output.emit(
        boards,
        [
            Column("Id", lambda b: b.get("id"), style="cyan"),
            Column("Name", lambda b: b.get("name"), style="bold"),
            Column("Type", lambda b: b.get("type")),
            Column("Project", lambda b: dig(b, "location", "projectKey")),
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
    data = session.client.get(f"{AGILE}/board/{board}")
    config = session.client.get(f"{AGILE}/board/{board}/configuration")
    if as_json:
        output.print_json({**data, "configuration": config})
        return
    columns = [c.get("name") for c in dig(config, "columnConfig", "columns", default=[])]
    rows = [
        ("Name", escape(data.get("name", ""))),
        ("Type", data.get("type")),
        ("Project", escape(dig(data, "location", "displayName", default=""))),
        ("Filter", f"{dig(config, 'filter', 'id')} [dim](acli-py filter view …)[/]"),
        ("Columns", escape(" → ".join(c for c in columns if c))),
        ("Estimation", escape(dig(config, "estimation", "field", "displayName", default=""))),
    ]
    output.console.print(output.details(f"Board {board}", rows))


@board_app.command("create")
@guarded
def board_create(
    name: Annotated[str, typer.Option("--name", help="Board name.")],
    filter_id: Annotated[int, typer.Option("--filter", help="Saved filter id that feeds it.")],
    board_type: Annotated[str, typer.Option("--type", "-t", help="scrum or kanban.")] = "kanban",
    project: Annotated[
        str | None,
        typer.Option("--project", "-p", help="Put it in this project (else your own board)."),
    ] = None,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Create a board from a saved filter."""
    if board_type not in ("scrum", "kanban"):
        raise fail("--type is scrum or kanban.")
    session = connect(dry_run)
    body: dict[str, Any] = {"name": name, "type": board_type, "filterId": filter_id}
    body["location"] = (
        {"type": "project", "projectKeyOrId": project.upper()}
        if project
        else {"type": "user", "projectKeyOrId": session.me}
    )
    result = session.client.post(f"{AGILE}/board", body)
    if as_json:
        output.print_json(result)
    if not session.dry_run:
        output.success(f"Created board [bold cyan]{result.get('id')}[/] {escape(name)}")


@board_app.command("delete")
@guarded
def board_delete(
    boards: Annotated[list[int], typer.Argument(help="Board ids.")],
    yes: YesOpt = False,
    ignore_errors: IgnoreErrorsOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Delete boards (their issues and filters stay)."""
    session = connect(dry_run)
    confirm(f"Delete {len(boards)} board(s)?", yes, session)
    run_bulk(
        [str(b) for b in boards],
        lambda b: session.client.delete(f"{AGILE}/board/{b}"),
        done="would be deleted" if session.dry_run else "deleted",
        ignore_errors=ignore_errors,
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
    session = connect()
    output.emit(
        session.client.paged(f"{AGILE}/board/{board}/project", limit=limit_of(limit, all_pages)),
        [
            Column("Key", lambda p: p.get("key"), style="cyan"),
            Column("Name", lambda p: p.get("name"), style="bold"),
            Column("Id", lambda p: p.get("id"), style="dim"),
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
    _issue_list(
        f"{AGILE}/board/{board}/backlog",
        jql,
        limit_of(limit, all_pages),
        fields,
        template,
        fmt(as_json, as_csv, out),
        empty="The backlog is empty.",
    )


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
    states = ",".join(s.strip() for v in state or [] for s in v.split(","))
    sprints = session.client.paged(
        f"{AGILE}/board/{board_id(session, board)}/sprint",
        limit=limit_of(limit, all_pages),
        state=states or None,
    )
    output.emit(sprints, SPRINT_COLUMNS, fmt(as_json, as_csv, out), empty="No sprints.")


@sprint_app.command("view")
@guarded
def sprint_view(sprint: SprintIdArg, as_json: JsonOpt = False) -> None:
    """Show a sprint."""
    session = connect()
    data = session.client.get(f"{AGILE}/sprint/{sprint}")
    if as_json:
        output.print_json(data)
        return
    rows = [
        ("Name", escape(data.get("name", ""))),
        ("State", data.get("state")),
        ("Board", data.get("originBoardId")),
        ("Start", when(data.get("startDate"))),
        ("End", when(data.get("endDate"))),
        ("Completed", when(data.get("completeDate"))),
        ("Goal", escape(data.get("goal") or "")),
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
    body = {
        "name": name,
        "originBoardId": board_id(session, board),
        "startDate": iso_date(start),
        "endDate": iso_date(end, end_of_day=True),
        "goal": goal,
    }
    result = session.client.post(
        f"{AGILE}/sprint", {k: v for k, v in body.items() if v is not None}
    )
    if as_json:
        output.print_json(result)
    if not session.dry_run:
        output.success(f"Created sprint [bold cyan]{result.get('id')}[/] {escape(name)}")


def _update_sprint(session: Session, sprint: int, changes: dict[str, Any], done: str) -> None:
    changes = {k: v for k, v in changes.items() if v is not None}
    if not changes:
        raise fail("Nothing to change. See [bold]acli-py sprint update --help[/].")
    session.client.post(f"{AGILE}/sprint/{sprint}", changes)
    if not session.dry_run:
        output.success(f"Sprint {sprint} {done}")


@sprint_app.command("update")
@guarded
def sprint_update(
    sprint: SprintIdArg,
    name: NameOpt = None,
    start: StartOpt = None,
    end: EndOpt = None,
    goal: GoalOpt = None,
    dry_run: DryRunOpt = False,
) -> None:
    """Rename a sprint or change its dates or goal."""
    session = connect(dry_run)
    _update_sprint(
        session,
        sprint,
        {"name": name, "startDate": iso_date(start), "endDate": iso_date(end, True), "goal": goal},
        "updated",
    )


@sprint_app.command("start")
@guarded
def sprint_start(
    sprint: SprintIdArg,
    start: StartOpt = None,
    end: EndOpt = None,
    weeks: Annotated[
        int, typer.Option("--weeks", min=1, max=8, help="Length when no --end is given.")
    ] = 2,
    goal: GoalOpt = None,
    dry_run: DryRunOpt = False,
) -> None:
    """Start a future sprint (now, for --weeks, unless dates are given)."""
    session = connect(dry_run)
    current = session.client.get(f"{AGILE}/sprint/{sprint}")
    if current.get("state") != "future":
        raise fail(f"Sprint {sprint} is {current.get('state')}; only a future sprint can start.")
    begin = (
        iso_date(start)
        or current.get("startDate")
        or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    )
    finish = iso_date(end, True) or current.get("endDate")
    if not finish:
        began = datetime.fromisoformat(begin.replace("Z", "+00:00"))
        finish = (began + timedelta(weeks=weeks)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    _update_sprint(
        session,
        sprint,
        {"state": "active", "startDate": begin, "endDate": finish, "goal": goal},
        "started",
    )


@sprint_app.command("close")
@guarded
def sprint_close(sprint: SprintIdArg, yes: YesOpt = False, dry_run: DryRunOpt = False) -> None:
    """Complete an active sprint. Unfinished issues go back to the backlog."""
    session = connect(dry_run)
    confirm(f"Close sprint {sprint}?", yes, session)
    _update_sprint(session, sprint, {"state": "closed"}, "closed")


@sprint_app.command("delete")
@guarded
def sprint_delete(
    sprints: Annotated[list[int], typer.Argument(help="Sprint ids.")],
    yes: YesOpt = False,
    ignore_errors: IgnoreErrorsOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Delete sprints; their issues move to the backlog."""
    session = connect(dry_run)
    confirm(f"Delete {len(sprints)} sprint(s)?", yes, session)
    run_bulk(
        [str(s) for s in sprints],
        lambda s: session.client.delete(f"{AGILE}/sprint/{s}"),
        done="would be deleted" if session.dry_run else "deleted",
        ignore_errors=ignore_errors,
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
    _issue_list(
        f"{AGILE}/sprint/{sprint}/issue",
        jql,
        limit_of(limit, all_pages),
        fields,
        template,
        fmt(as_json, as_csv, out),
        empty="No issues.",
    )


@sprint_app.command("add")
@guarded
def sprint_add(
    sprint: SprintIdArg,
    keys: KeysArg = None,
    jql: JqlOpt = None,
    dry_run: DryRunOpt = False,
) -> None:
    """Move issues into a sprint."""
    session = connect(dry_run)
    picked = resolve.targets(session.client, keys, jql)
    for start in range(0, len(picked), 50):
        session.client.post(
            f"{AGILE}/sprint/{sprint}/issue", {"issues": picked[start : start + 50]}
        )
    verb = "Would move" if session.dry_run else "Moved"
    output.success(f"{verb} {len(picked)} issue(s) into sprint {sprint}")


@sprint_app.command("remove")
@guarded
def sprint_remove(keys: KeysArg = None, jql: JqlOpt = None, dry_run: DryRunOpt = False) -> None:
    """Move issues out of their sprint, back to the backlog."""
    session = connect(dry_run)
    picked = resolve.targets(session.client, keys, jql)
    for start in range(0, len(picked), 50):
        session.client.post(f"{AGILE}/backlog/issue", {"issues": picked[start : start + 50]})
    verb = "Would move" if session.dry_run else "Moved"
    output.success(f"{verb} {len(picked)} issue(s) to the backlog")
