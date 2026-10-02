"""`acli-py filter` and `acli-py field`: saved filters and custom fields."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

import typer
from rich.markup import escape

from acli_py.application.commands.create_field.command import CreateField
from acli_py.application.commands.create_filter.command import CreateFilter
from acli_py.application.commands.delete_filter.command import DeleteFilter
from acli_py.application.commands.give_filter.command import GiveFilter
from acli_py.application.commands.restore_field.command import RestoreField
from acli_py.application.commands.set_filter_columns.command import SetFilterColumns
from acli_py.application.commands.star_filter.command import StarFilter
from acli_py.application.commands.trash_field.command import TrashField
from acli_py.application.commands.update_field.command import UpdateField
from acli_py.application.commands.update_filter.command import UpdateFilter
from acli_py.application.queries.get_filter.query import GetFilter
from acli_py.application.queries.list_fields.query import ListFields
from acli_py.application.queries.list_filter_columns.query import ListFilterColumns
from acli_py.application.queries.list_filters.query import ListFilters
from acli_py.application.queries.search_filters.query import SearchFilters
from acli_py.domain.fields import FIELD_TYPES
from acli_py.presentation import inputs, output
from acli_py.presentation.cli.common import (
    AllOpt,
    CsvOpt,
    DryRunOpt,
    JsonOpt,
    KeepGoingOpt,
    LimitOpt,
    OutputOpt,
    WebOpt,
    YesOpt,
    connect,
    fail,
    fmt,
    guarded,
    limit_of,
    open_url,
    run_many,
)
from acli_py.presentation.output import Column, dig

filter_app = typer.Typer(help="Work with saved filters.", no_args_is_help=True)
field_app = typer.Typer(help="List fields and manage custom fields.", no_args_is_help=True)

FilterIdArg = Annotated[str, typer.Argument(help="Filter id.")]

FILTER_COLUMNS = [
    Column("Id", lambda f: f["id"], style="cyan"),
    Column("Name", lambda f: f["name"], style="bold"),
    Column("Owner", lambda f: dig(f, "owner", "name")),
    Column("★", lambda f: "★" if f["favourite"] else "", style="yellow"),
    Column("JQL", lambda f: f["jql"], style="dim"),
]


def _shares(value: str | None, label: str) -> tuple[Mapping[str, Any], ...] | None:
    """Return share permissions given as a JSON array, or @file, or None when not given."""
    if value is None:
        return None
    try:
        data = json.loads(Path(value[1:]).read_text() if value.startswith("@") else value)
    except ValueError as error:
        raise fail(f"{label} must be a JSON array (or @file): {error}") from error
    if not isinstance(data, list) or not all(isinstance(p, dict) for p in data):
        raise fail(f"{label} must be a JSON array of share permissions.")
    return tuple(data)


# ── filters ──────────────────────────────────────────────────────────────────


@filter_app.command("list")
@guarded
def filter_list(
    favourites: Annotated[
        bool, typer.Option("--favourites", "--favorites", help="Your starred filters instead.")
    ] = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    out: OutputOpt = None,
) -> None:
    """List your own filters (or your favourites)."""
    found = connect().send(ListFilters(favourites))
    output.emit(found.to_json(), FILTER_COLUMNS, fmt(as_json, as_csv, out), empty="No filters.")


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
    out: OutputOpt = None,
) -> None:
    """Search every filter you can see."""
    found = connect().send(SearchFilters(name, owner, project, limit_of(limit, all_pages)))
    output.emit(
        found.to_json(), FILTER_COLUMNS, fmt(as_json, as_csv, out), empty="No filters match."
    )


@filter_app.command("view")
@guarded
def filter_view(filter_id: FilterIdArg, web: WebOpt = False, as_json: JsonOpt = False) -> None:
    """Show a filter."""
    session = connect()
    if web:
        open_url(f"{session.url}/issues/?filter={quote(filter_id)}")
        return
    found = session.send(GetFilter(filter_id))
    if as_json:
        output.print_json(found.to_json())
        return
    saved = found.filter
    rows = [
        ("Name", escape(saved.name)),
        ("Owner", escape(saved.owner.name if saved.owner else "")),
        ("JQL", escape(saved.jql)),
        ("Description", escape(saved.description)),
        ("Favourite", "★" if saved.favourite else ""),
        ("Shared with", escape(", ".join(saved.shared_with))),
        ("URL", escape(saved.url)),
    ]
    output.console.print(output.details(f"Filter {escape(filter_id)}", rows))


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
    command = CreateFilter(name, jql, description, favourite, _shares(share, "--share"))
    session = connect(dry_run)
    run_many(
        session,
        [command],
        done="would be created" if session.dry_run else "created",
        as_json=as_json,
        describe=lambda r: "" if session.dry_run else f"[dim](id {r.after.get('filter')})[/]",
    )


@filter_app.command("update")
@guarded
def filter_update(
    filter_id: FilterIdArg,
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    jql: Annotated[str | None, typer.Option("--jql", "-q", help="New query.")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    share: SharesOpt = None,
    edit_share: EditSharesOpt = None,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Change a filter's name, query, description or sharing."""
    command = UpdateFilter(
        filter_id,
        name,
        jql,
        description,
        _shares(share, "--share"),
        _shares(edit_share, "--edit-share"),
    )
    session = connect(dry_run)
    run_many(
        session,
        [command],
        done="would be updated" if session.dry_run else "updated",
        yes=yes,
        as_json=as_json,
    )


@filter_app.command("delete")
@guarded
def filter_delete(
    filter_ids: Annotated[list[str], typer.Argument(help="Filter ids.")],
    yes: YesOpt = False,
    keep_going: KeepGoingOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Delete filters."""
    session = connect(dry_run)
    run_many(
        session,
        [DeleteFilter(f) for f in filter_ids],
        done="would be deleted" if session.dry_run else "deleted",
        yes=yes,
        keep_going=keep_going,
        concurrency=1,
    )


@filter_app.command("star")
@guarded
def filter_star(
    filter_id: FilterIdArg,
    remove: Annotated[bool, typer.Option("--remove", help="Unstar it instead.")] = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Add a filter to your favourites (or --remove it)."""
    session = connect(dry_run)
    done = "unstarred" if remove else "starred"
    run_many(
        session,
        [StarFilter(filter_id, not remove)],
        done=f"would be {done}" if session.dry_run else done,
        yes=yes,
    )


@filter_app.command("owner")
@guarded
def filter_owner(
    to: Annotated[str, typer.Option("--to", help="New owner: email, name or account id.")],
    filter_ids: Annotated[
        list[str] | None,
        typer.Argument(help="Filter ids ('-' reads them from stdin).", show_default=False),
    ] = None,
    from_file: Annotated[
        Path | None,
        typer.Option(
            "--from-file", "-f", help="Read filter ids from a file (commas, spaces or lines)."
        ),
    ] = None,
    yes: YesOpt = False,
    keep_going: KeepGoingOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Hand filters over to someone else."""
    filter_ids = inputs.given(filter_ids) + (inputs.read_keys_file(from_file) if from_file else [])
    if not filter_ids:
        raise fail("Say which filters: give their ids or --from-file.")
    session = connect(dry_run)
    run_many(
        session,
        [GiveFilter(f, to) for f in filter_ids],
        done=f"{'would be ' if session.dry_run else ''}given to {escape(to)}",
        yes=yes,
        keep_going=keep_going,
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
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
    out: OutputOpt = None,
) -> None:
    """Show, set or reset the columns a filter shows in the issue navigator."""
    if set_to and reset:
        raise fail("Use --set or --reset, not both.")
    session = connect(dry_run)
    if set_to or reset:
        columns = tuple(c.strip() for value in set_to or [] for c in value.split(",") if c.strip())
        done = f"columns set to {', '.join(columns)}" if columns else "columns reset"
        run_many(
            session,
            [SetFilterColumns(filter_id, columns)],
            done=f"would have its {done}" if session.dry_run else done,
            yes=yes,
        )
        return
    output.emit(
        session.send(ListFilterColumns(filter_id)).to_json(),
        [
            Column("Field", lambda c: c["field"], style="dim"),
            Column("Label", lambda c: c["label"]),
        ],
        fmt(as_json, chosen=out),
    )


# ── fields ───────────────────────────────────────────────────────────────────


@field_app.command("list")
@guarded
def field_list(
    custom: Annotated[bool, typer.Option("--custom", "-c", help="Only custom fields.")] = False,
    query: Annotated[str | None, typer.Option("--query", "-q", help="Name or id contains.")] = None,
    trashed: Annotated[bool, typer.Option("--trashed", help="Custom fields in the trash.")] = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    out: OutputOpt = None,
) -> None:
    """List fields, with the ids to use in --field, --fields and JQL."""
    found = connect().send(ListFields(query, custom, trashed))
    output.emit(
        found.to_json(),
        [
            Column("Id", lambda f: f["id"], style="cyan", no_wrap=True),
            Column("Name", lambda f: f["name"], style="bold"),
            Column("Type", lambda f: f["type"]),
            Column("Custom", lambda f: "yes" if f["custom"] else ""),
            Column("JQL", lambda f: ", ".join(f["clauseNames"][:2]), style="dim"),
        ],
        fmt(as_json, as_csv, out),
        empty="No fields match.",
    )


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
    command = CreateField(name, field_type, description, searcher)
    session = connect(dry_run)
    run_many(
        session,
        [command],
        done="would be created" if session.dry_run else "created",
        as_json=as_json,
        describe=lambda r: "" if session.dry_run else f"[dim](id {r.after.get('field')})[/]",
    )


FieldIdArg = Annotated[str, typer.Argument(help="Custom field id, e.g. customfield_10042.")]


@field_app.command("update")
@guarded
def field_update(
    field_id: FieldIdArg,
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    searcher: Annotated[str | None, typer.Option("--searcher", help="New searcher key.")] = None,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Rename a custom field or change its description or searcher."""
    command = UpdateField(field_id, name, description, searcher)
    session = connect(dry_run)
    run_many(session, [command], done="would be updated" if session.dry_run else "updated", yes=yes)


@field_app.command("delete")
@guarded
def field_delete(field_id: FieldIdArg, yes: YesOpt = False, dry_run: DryRunOpt = False) -> None:
    """Move a custom field to the trash (restorable for 60 days)."""
    session = connect(dry_run)
    run_many(
        session,
        [TrashField(field_id)],
        done="would be moved to the trash" if session.dry_run else "moved to the trash",
        yes=yes,
    )


@field_app.command("restore")
@guarded
def field_restore(field_id: FieldIdArg, yes: YesOpt = False, dry_run: DryRunOpt = False) -> None:
    """Restore a custom field from the trash."""
    session = connect(dry_run)
    run_many(
        session,
        [RestoreField(field_id)],
        done="would be restored" if session.dry_run else "restored",
        yes=yes,
    )
