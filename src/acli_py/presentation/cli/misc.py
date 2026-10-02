"""`acli-py dashboard`, `acli-py user`, `acli-py meta` and `acli-py api`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape

from acli_py.application.commands.call_api.command import CallApi
from acli_py.application.queries.call_api.query import ApiGet
from acli_py.application.queries.get_dashboard.query import GetDashboard
from acli_py.application.queries.get_person.query import GetPerson
from acli_py.application.queries.list_dashboards.query import ListDashboards
from acli_py.application.queries.list_issue_types.query import ListIssueTypes
from acli_py.application.queries.list_priorities.query import ListPriorities
from acli_py.application.queries.list_resolutions.query import ListResolutions
from acli_py.application.queries.list_statuses.query import ListStatuses
from acli_py.application.queries.search_people.query import SearchPeople
from acli_py.presentation import output
from acli_py.presentation.cli.common import (
    AllOpt,
    CsvOpt,
    DryRunOpt,
    JsonOpt,
    LimitOpt,
    OutputOpt,
    WebOpt,
    connect,
    fail,
    fmt,
    guarded,
    limit_of,
    open_url,
    read_text,
)
from acli_py.presentation.output import Column, dig

dashboard_app = typer.Typer(help="Find dashboards.", no_args_is_help=True)
user_app = typer.Typer(help="Look people up.", no_args_is_help=True)
meta_app = typer.Typer(
    help="Site-wide lists: statuses, priorities, resolutions, issue types.", no_args_is_help=True
)

# ── dashboards ───────────────────────────────────────────────────────────────


@dashboard_app.command("list")
@guarded
def dashboard_list(
    name: Annotated[str | None, typer.Option("--name", "-q", help="Name contains.")] = None,
    owner: Annotated[str | None, typer.Option("--owner", help="Owner: email, name or @me.")] = None,
    limit: LimitOpt = 50,
    all_pages: AllOpt = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    out: OutputOpt = None,
) -> None:
    """Search dashboards."""
    found = connect().send(ListDashboards(name, owner, limit_of(limit, all_pages)))
    output.emit(
        found.to_json(),
        [
            Column("Id", lambda d: d["id"], style="cyan"),
            Column("Name", lambda d: d["name"], style="bold"),
            Column("Owner", lambda d: dig(d, "owner", "name")),
            Column("★", lambda d: "★" if d["favourite"] else "", style="yellow"),
            Column("URL", lambda d: d["url"], style="dim"),
        ],
        fmt(as_json, as_csv, out),
        empty="No dashboards match.",
    )


@dashboard_app.command("view")
@guarded
def dashboard_view(
    dashboard_id: Annotated[str, typer.Argument(help="Dashboard id.")],
    web: WebOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Show a dashboard."""
    session = connect()
    found = session.send(GetDashboard(dashboard_id))
    board = found.dashboard
    if web:
        open_url(board.url or f"{session.url}/jira/dashboards/{dashboard_id}")
        return
    if as_json:
        output.print_json(found.to_json())
        return
    rows = [
        ("Name", escape(board.name)),
        ("Owner", escape(board.owner.name if board.owner else "")),
        ("Description", escape(board.description)),
        ("Popularity", board.popularity),
        ("URL", escape(board.url)),
    ]
    output.console.print(output.details(f"Dashboard {escape(dashboard_id)}", rows))


# ── users ────────────────────────────────────────────────────────────────────

USER_COLUMNS = [
    Column("Name", lambda u: u["name"], style="bold"),
    Column("Email", lambda u: u["email"]),
    Column("Account id", lambda u: u["accountId"], style="dim"),
    Column("Type", lambda u: u["accountType"], style="dim"),
    Column("Active", lambda u: "yes" if u["active"] else "no"),
]


@user_app.command("search")
@guarded
def user_search(
    query: Annotated[str, typer.Argument(help="Part of a name or email.")],
    limit: LimitOpt = 50,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    out: OutputOpt = None,
) -> None:
    """Find people by name or email."""
    found = connect().send(SearchPeople(query, limit))
    output.emit(found.to_json(), USER_COLUMNS, fmt(as_json, as_csv, out), empty="Nobody matches.")


@user_app.command("view")
@guarded
def user_view(
    who: Annotated[str, typer.Argument(help="@me, email, account id or name.")] = "@me",
    as_json: JsonOpt = False,
) -> None:
    """Show a person's profile (yours by default)."""
    (data,) = connect().send(GetPerson(who)).to_json()
    if as_json:
        output.print_json(data)
        return
    rows = [
        ("Email", escape(data["email"] or "[hidden]")),
        ("Account id", data["accountId"]),
        ("Type", data["accountType"]),
        ("Time zone", data["timeZone"]),
        ("Locale", data["locale"]),
        ("Active", "yes" if data["active"] else "no"),
        ("Groups", escape(", ".join(data["groups"]))),
    ]
    output.console.print(output.details(escape(data["name"] or who), rows))


# ── meta ─────────────────────────────────────────────────────────────────────

NAME_COLUMNS = [
    Column("Id", lambda r: r["id"], style="dim"),
    Column("Name", lambda r: r["name"], style="bold"),
    Column("Description", lambda r: r["description"]),
]


@meta_app.command()
@guarded
def statuses(as_json: JsonOpt = False, as_csv: CsvOpt = False, out: OutputOpt = None) -> None:
    """List every status and its category."""
    output.emit(
        connect().send(ListStatuses()).to_json(),
        [
            Column("Id", lambda s: s["id"], style="dim"),
            Column("Name", lambda s: s["name"], style="bold"),
            Column("Category", lambda s: s["category"]),
            Column("Project", lambda s: s["projectId"], style="dim"),
        ],
        fmt(as_json, as_csv, out),
    )


@meta_app.command()
@guarded
def priorities(as_json: JsonOpt = False, as_csv: CsvOpt = False, out: OutputOpt = None) -> None:
    """List priorities."""
    found = connect().send(ListPriorities()).to_json()
    output.emit(found, NAME_COLUMNS, fmt(as_json, as_csv, out))


@meta_app.command()
@guarded
def resolutions(as_json: JsonOpt = False, as_csv: CsvOpt = False, out: OutputOpt = None) -> None:
    """List resolutions."""
    found = connect().send(ListResolutions()).to_json()
    output.emit(found, NAME_COLUMNS, fmt(as_json, as_csv, out))


@meta_app.command("issue-types")
@guarded
def issue_types(
    project: Annotated[
        str | None, typer.Option("--project", "-p", help="Only this project's types.")
    ] = None,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    out: OutputOpt = None,
) -> None:
    """List issue types."""
    output.emit(
        connect().send(ListIssueTypes(project)).to_json(),
        [
            *NAME_COLUMNS[:2],
            Column("Subtask", lambda t: "yes" if t["subtask"] else ""),
            Column("Level", lambda t: t["hierarchyLevel"], justify="right"),
            NAME_COLUMNS[2],
        ],
        fmt(as_json, as_csv, out),
    )


# ── raw API ──────────────────────────────────────────────────────────────────

API_ROOT = "/rest/api/3"  # where a path without a leading '/' goes
METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH")


@guarded
def api(
    method: Annotated[str, typer.Argument(help="GET, POST, PUT, DELETE or PATCH.")],
    path: Annotated[str, typer.Argument(help="Path, e.g. /rest/api/3/myself or just myself.")],
    data: Annotated[
        str | None,
        typer.Option("--data", "-d", help="JSON body, or @file, or '-' for stdin."),
    ] = None,
    query: Annotated[
        list[str] | None, typer.Option("--query", "-q", help="Query parameter KEY=VALUE.")
    ] = None,
    dry_run: DryRunOpt = False,
) -> None:
    """Call any Jira REST endpoint with your credentials and print the JSON.

    Writes honour --dry-run like every other command, and are kept in the audit log.

    [dim]acli-py api GET myself
    acli-py api POST /rest/api/3/issue -d @issue.json --dry-run[/]
    """
    method = method.upper()
    if method not in METHODS:
        raise fail(f"Unsupported method {escape(method)}.")
    if not path.startswith("/"):
        path = f"{API_ROOT}/{path}"
    params: dict[str, list[str]] = {}
    for item in query or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise fail(f"--query takes KEY=VALUE, got {escape(item)!r}.")
        params.setdefault(key, []).append(value)
    pairs = tuple((k, tuple(v)) for k, v in params.items())
    body = None
    if data is not None:
        from_file = Path(data[1:]) if data.startswith("@") else None
        text = read_text(None if from_file else data, from_file)
        body = json.loads(text) if text and text.strip() else None
    session = connect(dry_run)
    if method == "GET":
        result = session.send(ApiGet(path, pairs))
    else:
        result = session.send(CallApi(method, path, pairs, body))
        if session.dry_run:
            return
    if result is not None:
        output.print_json(result)
