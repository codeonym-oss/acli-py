"""`aj dashboard`, `aj user`, `aj meta` and `aj api`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.markup import escape

from acli_py import output, resolve
from acli_py.cli.common import (
    AllOpt,
    CsvOpt,
    DryRunOpt,
    JsonOpt,
    LimitOpt,
    WebOpt,
    connect,
    fail,
    fmt,
    guarded,
    limit_of,
    open_url,
)
from acli_py.client import API
from acli_py.output import Column, dig

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
) -> None:
    """Search dashboards."""
    session = connect()
    account = resolve.user(session.client, owner, session.me)["accountId"] if owner else None
    found = session.client.paged(
        f"{API}/dashboard/search",
        limit=limit_of(limit, all_pages),
        dashboardName=name,
        accountId=account,
        expand="owner,favourite",
        orderBy="name",
    )
    output.emit(
        found,
        [
            Column("Id", lambda d: d.get("id"), style="cyan"),
            Column("Name", lambda d: d.get("name"), style="bold"),
            Column("Owner", lambda d: dig(d, "owner", "displayName")),
            Column("★", lambda d: "★" if d.get("isFavourite") else "", style="yellow"),
            Column("URL", lambda d: d.get("view"), style="dim"),
        ],
        fmt(as_json, as_csv),
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
    data = session.client.get(f"{API}/dashboard/{dashboard_id}")
    if web:
        open_url(data.get("view") or f"{session.url}/jira/dashboards/{dashboard_id}")
        return
    if as_json:
        output.print_json(data)
        return
    rows = [
        ("Name", escape(data.get("name", ""))),
        ("Owner", escape(dig(data, "owner", "displayName", default=""))),
        ("Description", escape(data.get("description") or "")),
        ("Popularity", data.get("popularity")),
        ("URL", escape(data.get("view", ""))),
    ]
    output.console.print(output.details(f"Dashboard {dashboard_id}", rows))


# ── users ────────────────────────────────────────────────────────────────────

USER_COLUMNS = [
    Column("Name", lambda u: u.get("displayName"), style="bold"),
    Column("Email", lambda u: u.get("emailAddress")),
    Column("Account id", lambda u: u.get("accountId"), style="dim"),
    Column("Type", lambda u: u.get("accountType"), style="dim"),
    Column("Active", lambda u: "yes" if u.get("active", True) else "no"),
]


@user_app.command("search")
@guarded
def user_search(
    query: Annotated[str, typer.Argument(help="Part of a name or email.")],
    limit: LimitOpt = 50,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
) -> None:
    """Find people by name or email."""
    session = connect()
    found = session.client.get(f"{API}/user/search", query=query, maxResults=limit)
    output.emit(found, USER_COLUMNS, fmt(as_json, as_csv), empty="Nobody matches.")


@user_app.command("view")
@guarded
def user_view(
    who: Annotated[str, typer.Argument(help="@me, email, account id or name.")] = "@me",
    as_json: JsonOpt = False,
) -> None:
    """Show a person's profile (yours by default)."""
    session = connect()
    if who.lower() in resolve.ME:
        data = session.client.myself()
    else:
        account = resolve.user(session.client, who)["accountId"]
        data = session.client.get(f"{API}/user", accountId=account, expand="groups")
    if as_json:
        output.print_json(data)
        return
    groups = [g["name"] for g in dig(data, "groups", "items", default=[])]
    rows = [
        ("Email", escape(data.get("emailAddress") or "[hidden]")),
        ("Account id", data.get("accountId")),
        ("Type", data.get("accountType")),
        ("Time zone", data.get("timeZone")),
        ("Locale", data.get("locale")),
        ("Active", "yes" if data.get("active", True) else "no"),
        ("Groups", escape(", ".join(groups))),
    ]
    output.console.print(output.details(escape(data.get("displayName", who)), rows))


# ── meta ─────────────────────────────────────────────────────────────────────

NAME_COLUMNS = [
    Column("Id", lambda r: r.get("id"), style="dim"),
    Column("Name", lambda r: r.get("name"), style="bold"),
    Column("Description", lambda r: r.get("description")),
]


@meta_app.command()
@guarded
def statuses(as_json: JsonOpt = False, as_csv: CsvOpt = False) -> None:
    """List every status and its category."""
    session = connect()
    output.emit(
        session.client.get(f"{API}/status"),
        [
            Column("Id", lambda s: s.get("id"), style="dim"),
            Column("Name", lambda s: s.get("name"), style="bold"),
            Column("Category", lambda s: dig(s, "statusCategory", "name")),
            Column("Project", lambda s: dig(s, "scope", "project", "id"), style="dim"),
        ],
        fmt(as_json, as_csv),
    )


@meta_app.command()
@guarded
def priorities(as_json: JsonOpt = False, as_csv: CsvOpt = False) -> None:
    """List priorities."""
    session = connect()
    output.emit(session.client.paged(f"{API}/priority/search"), NAME_COLUMNS, fmt(as_json, as_csv))


@meta_app.command()
@guarded
def resolutions(as_json: JsonOpt = False, as_csv: CsvOpt = False) -> None:
    """List resolutions."""
    session = connect()
    output.emit(
        session.client.paged(f"{API}/resolution/search"), NAME_COLUMNS, fmt(as_json, as_csv)
    )


@meta_app.command("issue-types")
@guarded
def issue_types(
    project: Annotated[
        str | None, typer.Option("--project", "-p", help="Only this project's types.")
    ] = None,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
) -> None:
    """List issue types."""
    session = connect()
    if project:
        project_id = session.client.get(f"{API}/project/{project.upper()}")["id"]
        found = session.client.get(f"{API}/issuetype/project", projectId=project_id)
    else:
        found = session.client.get(f"{API}/issuetype")
    output.emit(
        found,
        [
            *NAME_COLUMNS[:2],
            Column("Subtask", lambda t: "yes" if t.get("subtask") else ""),
            Column("Level", lambda t: t.get("hierarchyLevel"), justify="right"),
            NAME_COLUMNS[2],
        ],
        fmt(as_json, as_csv),
    )


# ── raw API ──────────────────────────────────────────────────────────────────


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

    Writes honour --dry-run like every other command.

    [dim]aj api GET myself
    aj api POST /rest/api/3/issue -d @issue.json --dry-run[/]
    """
    method = method.upper()
    if method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
        raise fail(f"Unsupported method {escape(method)}.")
    if not path.startswith("/"):
        path = f"{API}/{path}"
    params: dict[str, Any] = {}
    for item in query or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise fail(f"--query takes KEY=VALUE, got {escape(item)!r}.")
        params.setdefault(key, []).append(value)
    body = None
    if data is not None:
        import sys

        text = (
            sys.stdin.read()
            if data == "-"
            else Path(data[1:]).read_text(encoding="utf-8")
            if data.startswith("@")
            else data
        )
        body = json.loads(text) if text.strip() else None
    session = connect(dry_run)
    result = session.client.request(
        method, path, params={k: v[0] if len(v) == 1 else v for k, v in params.items()}, body=body
    )
    if result is not None and not (session.dry_run and session.client.is_write(method, path)):
        output.print_json(result)
