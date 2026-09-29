"""`acli-py filter` and `acli-py field`: saved filters and custom fields."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

import typer
from rich.markup import escape

from acli_py.infrastructure.jira import resolve
from acli_py.infrastructure.jira.client import API
from acli_py.presentation import output
from acli_py.presentation.cli.common import (
    AllOpt,
    CsvOpt,
    DryRunOpt,
    IgnoreErrorsOpt,
    JsonOpt,
    LimitOpt,
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
)
from acli_py.presentation.output import Column, dig

filter_app = typer.Typer(help="Work with saved filters.", no_args_is_help=True)
field_app = typer.Typer(help="List fields and manage custom fields.", no_args_is_help=True)

FilterIdArg = Annotated[str, typer.Argument(help="Filter id.")]

FILTER_COLUMNS = [
    Column("Id", lambda f: f.get("id"), style="cyan"),
    Column("Name", lambda f: f.get("name"), style="bold"),
    Column("Owner", lambda f: dig(f, "owner", "displayName")),
    Column("★", lambda f: "★" if f.get("favourite") else "", style="yellow"),
    Column("JQL", lambda f: f.get("jql"), style="dim"),
]


def _share(value: str | None, label: str) -> list | None:
    if value is None:
        return None
    try:
        data = json.loads(Path(value[1:]).read_text() if value.startswith("@") else value)
    except ValueError as error:
        raise fail(f"{label} must be a JSON array (or @file): {error}") from error
    if not isinstance(data, list):
        raise fail(f"{label} must be a JSON array of share permissions.")
    return data


# ── filters ──────────────────────────────────────────────────────────────────


@filter_app.command("list")
@guarded
def filter_list(
    favourites: Annotated[
        bool, typer.Option("--favourites", "--favorites", help="Your starred filters instead.")
    ] = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
) -> None:
    """List your own filters (or your favourites)."""
    session = connect()
    path = f"{API}/filter/favourite" if favourites else f"{API}/filter/my"
    found = session.client.get(path, expand="favourite" if not favourites else None)
    if favourites:
        found = [{**f, "favourite": True} for f in found]
    output.emit(found, FILTER_COLUMNS, fmt(as_json, as_csv), empty="No filters.")


@filter_app.command("search")
@guarded
def filter_search(
    name: Annotated[str | None, typer.Option("--name", "-q", help="Name contains.")] = None,
    owner: Annotated[str | None, typer.Option("--owner", help="Owner: email, name or @me.")] = None,
    project: Annotated[
        str | None, typer.Option("--project", "-p", help="Shared with a project.")
    ] = None,
    limit: LimitOpt = 50,
    all_pages: AllOpt = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
) -> None:
    """Search every filter you can see."""
    session = connect()
    account = resolve.user(session.client, owner, session.me)["accountId"] if owner else None
    project_id = session.client.get(f"{API}/project/{project.upper()}")["id"] if project else None
    found = session.client.paged(
        f"{API}/filter/search",
        limit=limit_of(limit, all_pages),
        filterName=name,
        accountId=account,
        projectId=project_id,
        expand="owner,jql,favourite",
        orderBy="name",
    )
    output.emit(found, FILTER_COLUMNS, fmt(as_json, as_csv), empty="No filters match.")


@filter_app.command("view")
@guarded
def filter_view(filter_id: FilterIdArg, web: WebOpt = False, as_json: JsonOpt = False) -> None:
    """Show a filter."""
    session = connect()
    if web:
        open_url(f"{session.url}/issues/?filter={quote(filter_id)}")
        return
    data = session.client.get(f"{API}/filter/{filter_id}", expand="sharedUsers,subscriptions")
    if as_json:
        output.print_json(data)
        return
    shares = [
        dig(p, "group", "name") or dig(p, "project", "key") or p.get("type")
        for p in data.get("sharePermissions", [])
    ]
    rows = [
        ("Name", escape(data.get("name", ""))),
        ("Owner", escape(dig(data, "owner", "displayName", default=""))),
        ("JQL", escape(data.get("jql", ""))),
        ("Description", escape(data.get("description") or "")),
        ("Favourite", "★" if data.get("favourite") else ""),
        ("Shared with", escape(", ".join(str(s) for s in shares if s))),
        ("URL", escape(data.get("viewUrl", ""))),
    ]
    output.console.print(output.details(f"Filter {filter_id}", rows))


SharesOpt = Annotated[
    str | None, typer.Option("--share", help="Share permissions as a JSON array, or @file.")
]
EditSharesOpt = Annotated[
    str | None, typer.Option("--edit-share", help="Edit permissions as a JSON array, or @file.")
]


@filter_app.command("create")
@guarded
def filter_create(
    name: Annotated[str, typer.Option("--name", help="Filter name.")],
    jql: Annotated[str, typer.Option("--jql", "-q", help="The query.")],
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    favourite: Annotated[bool, typer.Option("--favourite/--no-favourite", help="Star it.")] = True,
    share: SharesOpt = None,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Save a JQL query as a filter."""
    session = connect(dry_run)
    body: dict[str, Any] = {"name": name, "jql": jql, "favourite": favourite}
    if description:
        body["description"] = description
    if (shares := _share(share, "--share")) is not None:
        body["sharePermissions"] = shares
    result = session.client.post(f"{API}/filter", body)
    if as_json:
        output.print_json(result)
    if not session.dry_run:
        output.success(f"Created filter [bold cyan]{result.get('id')}[/] {escape(name)}")


@filter_app.command("update")
@guarded
def filter_update(
    filter_id: FilterIdArg,
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    jql: Annotated[str | None, typer.Option("--jql", "-q", help="New query.")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    share: SharesOpt = None,
    edit_share: EditSharesOpt = None,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Change a filter's name, query, description or sharing."""
    session = connect(dry_run)
    current = session.client.get(f"{API}/filter/{filter_id}")
    # Jira's PUT needs the name even when it doesn't change.
    body: dict[str, Any] = {"name": name or current["name"]}
    if jql is not None:
        body["jql"] = jql
    if description is not None:
        body["description"] = description
    if (shares := _share(share, "--share")) is not None:
        body["sharePermissions"] = shares
    if (edits := _share(edit_share, "--edit-share")) is not None:
        body["editPermissions"] = edits
    if len(body) == 1 and not name:
        raise fail("Nothing to change. See [bold]acli-py filter update --help[/].")
    result = session.client.put(f"{API}/filter/{filter_id}", body)
    if as_json:
        output.print_json(result)
    if not session.dry_run:
        output.success(f"Updated filter {filter_id}")


@filter_app.command("delete")
@guarded
def filter_delete(
    filter_ids: Annotated[list[str], typer.Argument(help="Filter ids.")],
    yes: YesOpt = False,
    ignore_errors: IgnoreErrorsOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Delete filters."""
    session = connect(dry_run)
    confirm(f"Delete {len(filter_ids)} filter(s)?", yes, session)
    run_bulk(
        filter_ids,
        lambda fid: session.client.delete(f"{API}/filter/{fid}"),
        done="would be deleted" if session.dry_run else "deleted",
        ignore_errors=ignore_errors,
    )


@filter_app.command("star")
@guarded
def filter_star(
    filter_id: FilterIdArg,
    remove: Annotated[bool, typer.Option("--remove", help="Unstar it instead.")] = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Add a filter to your favourites (or --remove it)."""
    session = connect(dry_run)
    if remove:
        session.client.delete(f"{API}/filter/{filter_id}/favourite")
    else:
        session.client.put(f"{API}/filter/{filter_id}/favourite")
    if not session.dry_run:
        output.success(f"Filter {filter_id} {'unstarred' if remove else 'starred'}")


@filter_app.command("owner")
@guarded
def filter_owner(
    to: Annotated[str, typer.Option("--to", help="New owner: email, name or account id.")],
    filter_ids: Annotated[
        list[str] | None, typer.Argument(help="Filter ids.", show_default=False)
    ] = None,
    from_file: Annotated[
        Path | None,
        typer.Option(
            "--from-file", "-f", help="Read filter ids from a file (commas, spaces or lines)."
        ),
    ] = None,
    yes: YesOpt = False,
    ignore_errors: IgnoreErrorsOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Hand filters over to someone else."""
    filter_ids = resolve.split_keys(filter_ids) + (
        resolve.read_keys_file(from_file) if from_file else []
    )
    if not filter_ids:
        raise fail("Say which filters: give their ids or --from-file.")
    session = connect(dry_run)
    account = resolve.user(session.client, to, session.me)["accountId"]
    if len(filter_ids) > 1:
        confirm(f"Give {len(filter_ids)} filters to {to}?", yes, session)
    run_bulk(
        filter_ids,
        lambda fid: session.client.put(f"{API}/filter/{fid}/owner", {"accountId": account}),
        done=f"{'would be ' if session.dry_run else ''}given to {escape(to)}",
        ignore_errors=ignore_errors,
    )


@filter_app.command("columns")
@guarded
def filter_columns(
    filter_id: FilterIdArg,
    set_to: Annotated[
        list[str] | None,
        typer.Option("--set", help="Replace the columns with these field ids (repeatable)."),
    ] = None,
    reset: Annotated[bool, typer.Option("--reset", help="Go back to the default columns.")] = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Show, set or reset the columns a filter shows in the issue navigator."""
    session = connect(dry_run)
    path = f"{API}/filter/{filter_id}/columns"
    if set_to and reset:
        raise fail("Use --set or --reset, not both.")
    if reset:
        session.client.delete(path)
        if not session.dry_run:
            output.success(f"Filter {filter_id} columns reset")
        return
    if set_to:
        columns = [c.strip() for value in set_to for c in value.split(",") if c.strip()]
        session.client.put(path, {"columns": columns})
        if not session.dry_run:
            output.success(f"Filter {filter_id} columns set to {', '.join(columns)}")
        return
    output.emit(
        session.client.get(path),
        [
            Column("Field", lambda c: c.get("value"), style="dim"),
            Column("Label", lambda c: c.get("label")),
        ],
        fmt(as_json),
    )


# ── fields ───────────────────────────────────────────────────────────────────

CF = resolve.CUSTOM
FIELD_TYPES = {
    "text": ("textfield", "textsearcher"),
    "textarea": ("textarea", "textsearcher"),
    "number": ("float", "exactnumber"),
    "select": ("select", "multiselectsearcher"),
    "multiselect": ("multiselect", "multiselectsearcher"),
    "checkbox": ("multicheckboxes", "multiselectsearcher"),
    "radio": ("radiobuttons", "multiselectsearcher"),
    "date": ("datepicker", "daterange"),
    "datetime": ("datetime", "datetimerange"),
    "url": ("url", "exacttextsearcher"),
    "labels": ("labels", "labelsearcher"),
    "user": ("userpicker", "userpickergroupsearcher"),
    "multiuser": ("multiuserpicker", "userpickergroupsearcher"),
    "group": ("grouppicker", "grouppickersearcher"),
}


@field_app.command("list")
@guarded
def field_list(
    custom: Annotated[bool, typer.Option("--custom", "-c", help="Only custom fields.")] = False,
    query: Annotated[str | None, typer.Option("--query", "-q", help="Name or id contains.")] = None,
    trashed: Annotated[bool, typer.Option("--trashed", help="Custom fields in the trash.")] = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
) -> None:
    """List fields, with the ids to use in --field, --fields and JQL."""
    session = connect()
    if trashed:
        found = list(session.client.paged(f"{API}/field/search/trashed", query=query))
    else:
        found = session.client.fields()
        if custom:
            found = [f for f in found if f.get("custom")]
        if query:
            q = query.lower()
            found = [f for f in found if q in f.get("name", "").lower() or q in f["id"].lower()]
    found = sorted(found, key=lambda f: (bool(f.get("custom")), f.get("name", "").lower()))
    output.emit(
        found,
        [
            Column("Id", lambda f: f.get("id"), style="cyan", no_wrap=True),
            Column("Name", lambda f: f.get("name"), style="bold"),
            Column("Type", lambda f: _field_type(f)),
            Column("Custom", lambda f: "yes" if f.get("custom") else ""),
            Column("JQL", lambda f: ", ".join((f.get("clauseNames") or [])[:2]), style="dim"),
        ],
        fmt(as_json, as_csv),
        empty="No fields match.",
    )


def _field_type(field: dict) -> str:
    schema = field.get("schema") or {}
    custom = schema.get("custom", "")
    kind = custom.split(":")[-1] if custom else schema.get("type", "")
    if schema.get("type") == "array" and not custom:
        kind = f"{schema.get('items')}[]"
    return kind


@field_app.command("create")
@guarded
def field_create(
    name: Annotated[str, typer.Option("--name", help="Field name.")],
    field_type: Annotated[
        str,
        typer.Option("--type", "-t", help=f"{', '.join(FIELD_TYPES)}, or a full Jira type key."),
    ],
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    searcher: Annotated[
        str | None, typer.Option("--searcher", help="Searcher key (default fits the type).")
    ] = None,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Create a custom field."""
    if field_type.lower() in FIELD_TYPES:
        kind, default_searcher = FIELD_TYPES[field_type.lower()]
        type_key, searcher_key = CF + kind, searcher or CF + default_searcher
    elif ":" in field_type:
        type_key, searcher_key = field_type, searcher
    else:
        raise fail(
            f"Unknown field type {escape(field_type)!r}. Use one of: {', '.join(FIELD_TYPES)}."
        )
    session = connect(dry_run)
    body = {"name": name, "type": type_key, "searcherKey": searcher_key, "description": description}
    result = session.client.post(f"{API}/field", {k: v for k, v in body.items() if v})
    if as_json:
        output.print_json(result)
    if not session.dry_run:
        output.success(f"Created field [bold cyan]{result.get('id')}[/] {escape(name)}")


FieldIdArg = Annotated[str, typer.Argument(help="Custom field id, e.g. customfield_10042.")]


@field_app.command("update")
@guarded
def field_update(
    field_id: FieldIdArg,
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    searcher: Annotated[str | None, typer.Option("--searcher", help="New searcher key.")] = None,
    dry_run: DryRunOpt = False,
) -> None:
    """Rename a custom field or change its description or searcher."""
    body = {"name": name, "description": description, "searcherKey": searcher}
    body = {k: v for k, v in body.items() if v is not None}
    if not body:
        raise fail("Nothing to change. See [bold]acli-py field update --help[/].")
    session = connect(dry_run)
    session.client.put(f"{API}/field/{field_id}", body)
    if not session.dry_run:
        output.success(f"Updated field {escape(field_id)}")


@field_app.command("delete")
@guarded
def field_delete(field_id: FieldIdArg, yes: YesOpt = False, dry_run: DryRunOpt = False) -> None:
    """Move a custom field to the trash (restorable for 60 days)."""
    session = connect(dry_run)
    confirm(f"Move field {field_id} to the trash?", yes, session)
    session.client.post(f"{API}/field/{field_id}/trash")
    if not session.dry_run:
        output.success(f"Field {escape(field_id)} moved to the trash")


@field_app.command("restore")
@guarded
def field_restore(field_id: FieldIdArg, dry_run: DryRunOpt = False) -> None:
    """Restore a custom field from the trash."""
    session = connect(dry_run)
    session.client.post(f"{API}/field/{field_id}/restore")
    if not session.dry_run:
        output.success(f"Field {escape(field_id)} restored")
