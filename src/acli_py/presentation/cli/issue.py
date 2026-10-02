"""`acli-py issue`: view, search, create, edit, move, assign, watch, clone, archive, delete."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

import typer
from rich.markup import escape
from rich.table import Table

from acli_py.application.bulk import CONCURRENCY, MAX_CONCURRENCY
from acli_py.application.commands.archive_issue.command import ArchiveIssue
from acli_py.application.commands.assign_issue.command import AssignIssue
from acli_py.application.commands.clone_issue.command import CloneIssue
from acli_py.application.commands.create_issue.command import CreateIssue
from acli_py.application.commands.delete_issue.command import DeleteIssue
from acli_py.application.commands.edit_issue.command import EditIssue
from acli_py.application.commands.transition_issue.command import TransitionIssue
from acli_py.application.commands.watch_issue.command import WatchIssue
from acli_py.application.queries.compile_search.query import (
    ME,
    NOBODY,
    CompileSearch,
    NothingToSearchError,
)
from acli_py.application.queries.count_issues.query import CountIssues
from acli_py.application.queries.export_issues.query import ExportIssues
from acli_py.application.queries.get_history.query import GetHistory
from acli_py.application.queries.get_issue.query import GetIssue
from acli_py.application.queries.issue_columns import columns, split
from acli_py.application.queries.plan_import.query import PlanImport
from acli_py.application.queries.search_issues.query import SearchIssues
from acli_py.domain import adf
from acli_py.domain.jql.smart import cheatsheet
from acli_py.domain.values import when
from acli_py.infrastructure.jira import fields as issue_fields
from acli_py.infrastructure.jira import resolve
from acli_py.infrastructure.jira.client import DRY_RUN_ID
from acli_py.infrastructure.jira.fields import IssueInput, flat
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
    ProjectOpt,
    Session,
    WebOpt,
    YesOpt,
    connect,
    edit_text,
    fail,
    fmt,
    guarded,
    limit_of,
    open_url,
    pick_issues,
    plural,
    run_many,
    show_issues,
    template_of,
)
from acli_py.presentation.output import Column, Format, dig
from acli_py.presentation.writers import ExportFormat, IssueWriter

app = typer.Typer(help="Work with issues (Jira's work items).", no_args_is_help=True)

# ── shared field options (create and edit) ───────────────────────────────────

SummaryOpt = Annotated[str | None, typer.Option("--summary", "-s", help="One-line title.")]
DescriptionOpt = Annotated[
    str | None,
    typer.Option("--description", "-d", help="Markdown (or ADF JSON). '-' reads standard input."),
]
DescriptionFileOpt = Annotated[
    Path | None,
    typer.Option("--description-file", "-D", help="Read the description from a file."),
]
TypeOpt = Annotated[
    str | None, typer.Option("--type", "-t", help="Issue type: Task, Bug, Story, Epic…")
]
AssigneeOpt = Annotated[
    str | None,
    typer.Option("--assignee", "-a", help="Email, account id, name, @me, 'default' or 'none'."),
]
ReporterOpt = Annotated[
    str | None, typer.Option("--reporter", help="Email, account id, name or @me.")
]
PriorityOpt = Annotated[str | None, typer.Option("--priority", "-P", help="Priority name.")]
LabelOpt = Annotated[
    list[str] | None, typer.Option("--label", "-L", help="Label (repeat, or comma-separate).")
]
ComponentOpt = Annotated[
    list[str] | None, typer.Option("--component", "-C", help="Component name (repeatable).")
]
FixVersionOpt = Annotated[
    list[str] | None, typer.Option("--fix-version", help="Fix version name (repeatable).")
]
ParentOpt = Annotated[str | None, typer.Option("--parent", help="Parent issue key (epic, story).")]
DueOpt = Annotated[str | None, typer.Option("--due", help="Due date, YYYY-MM-DD ('' clears).")]
FieldOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--field",
        "-F",
        help="Any field: 'Story Points=5', 'Team=Blue', or raw JSON with 'NAME:=JSON'.",
    ),
]


def description_of(text: str | None, file: Path | None) -> str | None:
    """Return the description from -d, -D or stdin."""
    return resolve.read_text_arg(text, file)


# ── view ─────────────────────────────────────────────────────────────────────


@app.command()
@guarded
def view(
    key: Annotated[str, typer.Argument(help="Issue key, e.g. DEMO-12.")],
    fields: Annotated[
        str | None,
        typer.Option(
            "--fields", help="Extra fields to show, comma-separated ('*all' for everything)."
        ),
    ] = None,
    comments: Annotated[
        int, typer.Option("--comments", "-c", min=0, help="How many recent comments to show.")
    ] = 3,
    web: WebOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Show an issue: its details, description, subtasks, links and latest comments.

    [bold]--json[/] prints the issue with plain names (status, assignee, links, comments…),
    Markdown text and ISO dates; fields asked for with [bold]--fields[/] are under "fields".

    [dim]acli-py issue view DEMO-12
    acli-py issue view DEMO-12 --fields customfield_10016 -c 10
    acli-py issue view DEMO-12 --json | jq -r .status.name[/]
    """
    session = connect()
    key = key.upper()
    if web:
        open_url(session.browse(key))
        return
    extra = tuple(f.strip() for f in (fields or "").split(",") if f.strip())
    issue_view = session.send(GetIssue(key, extra))
    if as_json:
        output.print_json(issue_view.to_json())
        return
    output.console.print(issue_view.to_rich(comments=comments))


# ── search ───────────────────────────────────────────────────────────────────


AssigneeFilterOpt = Annotated[
    str | None, typer.Option("--assignee", "-a", help="@me, 'none', email or name.")
]
StatusFilterOpt = Annotated[
    list[str] | None, typer.Option("--status", "-s", help="Status name (repeatable).")
]
TypeFilterOpt = Annotated[
    list[str] | None, typer.Option("--type", "-t", help="Issue type (repeatable).")
]
LabelFilterOpt = Annotated[
    list[str] | None, typer.Option("--label", "-L", help="Label (repeatable).")
]
TextOpt = Annotated[str | None, typer.Option("--text", "-T", help="Full-text search.")]
OpenOpt = Annotated[bool, typer.Option("--open", "-o", help="Only issues not done yet.")]
SavedFilterOpt = Annotated[
    str | None, typer.Option("--filter", help="Use a saved filter's JQL (by id).")
]
RawOpt = Annotated[
    bool, typer.Option("--raw", help="Send the query as JQL, never as a smart query.")
]
QueryArg = Annotated[
    str | None,
    typer.Argument(
        help="A smart query ('@me #web is:open', see --syntax) or JQL (optional).",
        show_default=False,
    ),
]


def show_syntax() -> None:
    """Print the smart query syntax."""
    table = Table(title="Smart queries", title_justify="left", box=None, padding=(0, 2))
    table.add_column("Term", style="cyan", no_wrap=True)
    table.add_column("Also", style="dim")
    table.add_column("Meaning")
    for term, aliases, meaning in cheatsheet():
        table.add_row(escape(term), escape(aliases), escape(meaning))
    output.console.print(table)
    output.console.print(
        "\nTerms combine with AND; the same filter twice means either (s:todo s:review). "
        "Anything with =, ~, 'in (' or ORDER BY is sent as JQL."
    )


def _who(session: Session, assignee: str | None) -> str:
    """Return the assignee as `CompileSearch` takes it: ME, NOBODY or an account id."""
    who = (assignee or "").strip()
    if who.lower() in resolve.ME:
        return ME
    if who.lower() in resolve.NOBODY:
        return NOBODY
    return session.account_id(who) if who else ""


def compiled_search(
    session: Session,
    query: str | None = None,
    *,
    raw: bool = False,
    saved_filter: str | None = None,
    project: str | None = None,
    assignee: str | None = None,
    status: list[str] | None = None,
    issue_type: list[str] | None = None,
    label: list[str] | None = None,
    text: str | None = None,
    open_only: bool = False,
    order: str | None = None,
) -> str:
    """Return the JQL a search runs, warning about smart query terms that didn't fit."""
    try:
        compiled = session.send(
            CompileSearch(
                text=query or "",
                raw=raw,
                saved_filter=saved_filter or "",
                project=project or "",
                assignee=_who(session, assignee),
                statuses=tuple(flat(status) or ()),
                types=tuple(flat(issue_type) or ()),
                labels=tuple(flat(label) or ()),
                words=text or "",
                open_only=open_only,
                order=order or "",
                default_project=session.config.defaults.get("project") or "",
            )
        )
    except NothingToSearchError:
        raise fail(
            "Say what to search: a query, or --project/--assignee/--status/--text…, "
            "or set a default with [bold]acli-py config set project KEY[/]."
        ) from None
    for warning in compiled.warnings:
        output.warn(escape(warning))
    return compiled.jql


def print_count(session: Session, jql: str, as_json: bool) -> None:
    """Print how many issues `jql` matches."""
    number = session.send(CountIssues(jql))
    if as_json:
        output.print_json({"jql": jql, "count": number})
    else:
        output.console.print(number)


@app.command("search")
@app.command("list", hidden=True)
@guarded
def search(
    jql: QueryArg = None,
    project: ProjectOpt = None,
    assignee: AssigneeFilterOpt = None,
    status: StatusFilterOpt = None,
    issue_type: TypeFilterOpt = None,
    label: LabelFilterOpt = None,
    text: TextOpt = None,
    open_only: OpenOpt = False,
    saved_filter: SavedFilterOpt = None,
    order: Annotated[
        str | None,
        typer.Option("--order", help="Sort field; prefix '-' for descending, e.g. -created."),
    ] = None,
    fields: FieldsOpt = None,
    template: FormatOpt = None,
    limit: LimitOpt = 50,
    all_pages: AllOpt = False,
    count: Annotated[bool, typer.Option("--count", help="Only print how many match.")] = False,
    web: WebOpt = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    out: OutputOpt = None,
    syntax: Annotated[
        bool, typer.Option("--syntax", help="Show the smart query syntax and exit.")
    ] = False,
    raw: RawOpt = False,
) -> None:
    r"""Find issues with a smart query, JQL, and/or simple options.

    [dim]acli-py issue search '@me is:open #web sort:-priority'
    acli-py issue search 'p:DEMO s:progress updated:7d "login"'
    acli-py issue search -p DEMO -a @me --open --fields key,status,due
    acli-py issue search 'project = DEMO AND sprint in openSprints()' --csv
    acli-py issue search @me --format '{key}\t{status}\t{summary}'[/]
    """
    if syntax:
        show_syntax()
        return
    chosen = fmt(as_json, as_csv, out)
    shape = template_of(template, chosen)
    session = connect()
    query = compiled_search(
        session,
        jql,
        raw=raw,
        saved_filter=saved_filter,
        project=project,
        assignee=assignee,
        status=status,
        issue_type=issue_type,
        label=label,
        text=text,
        open_only=open_only,
        order=order,
    )
    if web:
        open_url(f"{session.url}/issues/?jql={quote(query)}")
        return
    if count:
        print_count(session, query, as_json)
        return
    names = (*split(fields), *(shape.names if shape else ()))
    with output.errors.status("Searching…"):
        view = session.send(SearchIssues(query, limit_of(limit, all_pages), names))
    show_issues(view, chosen, shape, empty="No issues match.")
    if chosen is Format.table and shape is None and view.issues:
        more = "" if not view.next_token else " (use --all for every page)"
        output.info(f"{plural(len(view.issues), 'issue')}{more} · [dim]{escape(query)}[/]")


@app.command()
@guarded
def count(
    jql: QueryArg = None,
    project: ProjectOpt = None,
    assignee: AssigneeFilterOpt = None,
    status: StatusFilterOpt = None,
    issue_type: TypeFilterOpt = None,
    label: LabelFilterOpt = None,
    text: TextOpt = None,
    open_only: OpenOpt = False,
    saved_filter: SavedFilterOpt = None,
    as_json: JsonOpt = False,
    raw: RawOpt = False,
) -> None:
    """Count the issues a search finds (Jira's estimate), with the same query and options.

    [dim]acli-py issue count '@me is:open'
    acli-py issue count -p DEMO -s 'In Progress' --json[/]
    """
    session = connect()
    query = compiled_search(
        session,
        jql,
        raw=raw,
        saved_filter=saved_filter,
        project=project,
        assignee=assignee,
        status=status,
        issue_type=issue_type,
        label=label,
        text=text,
        open_only=open_only,
    )
    print_count(session, query, as_json)


@app.command()
@guarded
def history(
    key: Annotated[str, typer.Argument(help="Issue key.")],
    field: Annotated[
        str | None,
        typer.Option("--field", "-f", help="Only this field's changes (name or id)."),
    ] = None,
    newest_first: Annotated[
        bool, typer.Option("--newest-first", "-r", help="Newest change first.")
    ] = False,
    limit: Annotated[
        int | None, typer.Option("--limit", "-l", min=1, help="Show at most this many changes.")
    ] = None,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    out: OutputOpt = None,
) -> None:
    """Show who changed what on an issue, and when.

    [dim]acli-py issue history DEMO-12
    acli-py issue history DEMO-12 --field status --newest-first[/]
    """
    session = connect()
    view = session.send(GetHistory(key, field or "", newest_first, limit))
    output.emit(
        view.to_json(),
        [
            Column("When", lambda r: when(r["at"]), no_wrap=True),
            Column("Who", lambda r: dig(r, "author", "name"), style="bold", no_wrap=True),
            Column("Field", lambda r: r["field"], style="cyan", no_wrap=True),
            Column("From", lambda r: r["from"]),
            Column("To", lambda r: r["to"]),
        ],
        fmt(as_json, as_csv, out),
        empty=f"No changes to {view.key}" + (f" in {field}." if field else "."),
    )


# ── create ───────────────────────────────────────────────────────────────────


@app.command()
@guarded
def create(
    project: ProjectOpt = None,
    issue_type: TypeOpt = None,
    summary: SummaryOpt = None,
    description: DescriptionOpt = None,
    description_file: DescriptionFileOpt = None,
    assignee: AssigneeOpt = None,
    reporter: ReporterOpt = None,
    priority: PriorityOpt = None,
    label: LabelOpt = None,
    component: ComponentOpt = None,
    fix_version: FixVersionOpt = None,
    parent: ParentOpt = None,
    due: DueOpt = None,
    field: FieldOpt = None,
    editor: Annotated[
        bool, typer.Option("--editor", "-e", help="Write the summary and description in $EDITOR.")
    ] = False,
    from_json: Annotated[
        Path | None,
        typer.Option(
            "--from-json",
            help="Create from JSON: one issue, a list, or JSON lines; '-' reads stdin.",
        ),
    ] = None,
    from_csv: Annotated[
        Path | None,
        typer.Option("--from-csv", help="Create one issue per row of a CSV file with a header."),
    ] = None,
    from_file: Annotated[
        Path | None,
        typer.Option(
            "--from-file",
            "-f",
            help="Read the summary (first line) and description (the rest) from a text file.",
        ),
    ] = None,
    template: Annotated[
        bool, typer.Option("--template", help="Print an example --from-json file and exit.")
    ] = False,
    web: Annotated[bool, typer.Option("--open", help="Open the new issue in the browser.")] = False,
    concurrency: Annotated[
        int,
        typer.Option(
            "--concurrency",
            "-c",
            min=1,
            max=MAX_CONCURRENCY,
            help="How many issues to create at once (1 keeps the new keys in file order).",
        ),
    ] = 1,
    keep_going: KeepGoingOpt = False,
    force: ForceOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Create an issue, or many from JSON (a file, or JSON lines on stdin) or a CSV file.

    Options given on the command line fill in what each row leaves out. One issue is created
    straight away; many are listed first and asked about once ([bold]--yes[/] skips it). Each
    new key is kept in the audit log. Exits 0 when all were created, 1 when some failed, 2 when
    nothing ran.

    [dim]acli-py issue create -p DEMO -t Bug -s "Login fails on Safari" -a @me -L web
    acli-py issue create --from-csv backlog.csv -p DEMO --dry-run
    cat new.jsonl | acli-py issue create --from-json - -p DEMO -y[/]
    """
    if template:
        output.print_json([issue_fields.TEMPLATE])
        return
    session = connect(dry_run)
    common = IssueInput(
        project=project,
        type=issue_type,
        summary=summary,
        description=description_of(description, description_file),
        assignee=assignee,
        reporter=reporter,
        priority=priority,
        labels=flat(label),
        components=flat(component),
        fix_versions=flat(fix_version),
        parent=parent,
        due=due,
        extra=list(field or []),
    )
    if from_json or from_csv:
        if from_json and from_csv:
            raise fail("Give one of --from-json and --from-csv.")
        rows = issue_fields.read_rows(from_json or from_csv)  # type: ignore[arg-type]
        if not rows:
            raise fail("No issues to create.")
        wanted = [_merge(IssueInput.from_mapping(row), common) for row in rows]
        for n, item in enumerate(wanted, 1):
            if not item.raw and not item.summary:
                raise fail(f"Row {n} has no summary.")
        run_many(
            session,
            _creations(session, wanted),
            done="would be created" if session.dry_run else "created",
            yes=yes,
            concurrency=concurrency,
            keep_going=keep_going,
            force=force,
            as_json=as_json,
            describe=lambda changed: _created_as(session, changed),
        )
        return
    if from_file:
        text = resolve.read_text_arg(None, from_file) or ""
        first, _, rest = text.strip("\n").partition("\n")
        common.summary = common.summary or first.strip()
        common.description = common.description or rest.strip() or None
    if editor:
        common.summary, common.description = _edit_issue_text(
            session, common.summary or "", common.description or ""
        )
    if not common.summary:
        raise fail('A summary is required: pass [bold]-s "…"[/] or use [bold]--editor[/].')
    report = run_many(
        session,
        _creations(session, [common]),
        done="would be created" if session.dry_run else "created",
        yes=yes,
        as_json=as_json,
        line=lambda changed: (
            "Would create the issue above."
            if session.dry_run
            else f"Created [bold cyan]{escape(changed.key)}[/]  "
            f"{escape(session.browse(changed.key))}"
        ),
    )
    if web and not session.dry_run:
        open_url(session.browse(report.succeeded[0].result.key))


def _creations(session: Session, wanted: list[IssueInput]) -> list[CreateIssue]:
    """Return one `CreateIssue` per issue, its fields resolved (names to ids) on the site."""
    catalog = resolve.FieldCatalog.load(session.client) if any(w.extra for w in wanted) else None
    commands = []
    for n, item in enumerate(wanted, 1):
        item = _defaults(session, item)
        fields = issue_fields.build(
            session.client, item, me=session.me, creating=True, catalog=catalog
        )
        commands.append(CreateIssue(fields, item.raw.get("update") or {}, f"#{n}"))
    return commands


def _created_as(session: Session, changed: Any) -> str:
    """Return how a created issue reads in a report: 'as DEMO-9' (nothing in a dry run)."""
    return "" if changed.key == DRY_RUN_ID else f"as [bold cyan]{escape(changed.key)}[/]"


def _defaults(session: Session, wanted: IssueInput) -> IssueInput:
    if not wanted.raw:
        wanted.project = session.project(wanted.project)
        wanted.type = wanted.type or session.config.defaults.get("issue-type") or "Task"
    return wanted


def _merge(row: IssueInput, common: IssueInput) -> IssueInput:
    if row.raw:
        return row
    for name in ("project", "type", "assignee", "reporter", "priority", "parent", "due"):
        if getattr(row, name) is None:
            setattr(row, name, getattr(common, name))
    for name in ("labels", "components", "fix_versions"):
        if getattr(row, name) is None:
            setattr(row, name, getattr(common, name))
    if row.description is None:
        row.description = common.description
    row.extra = [*common.extra, *row.extra]
    return row


# ── export and import ────────────────────────────────────────────────────────


@app.command("export")
@guarded
def export(
    jql: Annotated[
        str | None,
        typer.Argument(help="A smart query or JQL (default: the default project)."),
    ] = None,
    saved_filter: Annotated[
        str | None, typer.Option("--filter", help="Export a saved filter's issues.")
    ] = None,
    fields: FieldsOpt = None,
    as_format: Annotated[
        ExportFormat | None,
        typer.Option("--as", help="csv, json, jsonl or markdown (default: from -o, else csv)."),
    ] = None,
    to: Annotated[
        Path | None, typer.Option("--to", "-o", help="Write to this file instead of stdout.")
    ] = None,
    limit: Annotated[
        int | None, typer.Option("--limit", "-l", min=1, help="Stop after this many issues.")
    ] = None,
) -> None:
    """Write every issue a search finds as CSV, JSON, JSON lines or a Markdown table.

    Issues are fetched a page at a time and written as they come, so exports of any size
    work. Columns are --fields (as for `issue search`). `issue import` reads the file back.

    [dim]acli-py issue export 'p:DEMO is:open' --fields key,summary,priority,labels -o open.csv
    acli-py issue export '@me is:open' --as markdown[/]
    """
    session = connect()
    query = compiled_search(session, jql, saved_filter=saved_filter)
    names = split(fields)
    chosen = as_format or ExportFormat.of(to)
    with to.open("w", encoding="utf-8", newline="") if to else nullcontext(sys.stdout) as out:
        writer = IssueWriter(out, columns(names), chosen)

        async def write_all() -> None:
            async with session.bus.stream(ExportIssues(query, names, limit)) as issues:
                async for issue in issues:
                    writer.write(issue)

        asyncio.run(write_all())
        writer.close()
    if to:
        output.success(f"Wrote {plural(writer.count, 'issue')} to {escape(str(to))}")


# ── import ───────────────────────────────────────────────────────────────────


@app.command("import")
@guarded
def import_(
    file: Annotated[
        Path,
        typer.Argument(
            help="CSV with a header, JSON (an object, a list) or JSON lines; '-' reads JSON "
            "from stdin.",
        ),
    ],
    project: Annotated[
        str | None,
        typer.Option("--project", "-p", help="Project for new issues without a project column."),
    ] = None,
    issue_type: Annotated[
        str | None, typer.Option("--type", "-t", help="Type of new issues (default: Task).")
    ] = None,
    concurrency: ConcurrencyOpt = CONCURRENCY,
    keep_going: KeepGoingOpt = False,
    force: ForceOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Update issues from a file, by key, and create the rows without one.

    Columns are the names `issue search --fields` and `issue export` use (summary, priority,
    labels, due…) or any field's name or id. A row with a key changes only what differs from
    the issue now; status, created, updated and resolution are skipped. Shows how the columns
    map to fields and each row's change, asks once, then runs a few rows at a time. The run is
    one audit record: `acli-py undo` puts the edits back. Exits 0 when every row worked, 1
    when some failed, 2 when nothing ran.

    [dim]acli-py issue export 'p:DEMO is:open' --fields key,summary,priority,labels -o open.csv
    acli-py issue import open.csv --dry-run[/]
    """
    rows = issue_fields.read_rows(file)
    session = connect(dry_run)
    defaults = session.config.defaults
    plan = session.send(
        PlanImport(
            tuple(rows),
            (project or defaults.get("project") or "").upper() or None,
            issue_type or defaults.get("issue-type") or "Task",
        )
    )
    mapping = Table(box=None, pad_edge=False, header_style="bold dim")
    mapping.add_column("Column")
    mapping.add_column("Field", style="cyan")
    for column, target in plan.mapping:
        mapping.add_row(escape(column), escape(target))
    output.errors.print(mapping)
    for ref, why in plan.problems:
        output.error(f"{escape(ref)}: {escape(why)}")
    if plan.unchanged:
        output.info(f"{plural(len(plan.unchanged), 'row')} match their issue already.")
    if plan.steps:
        run_many(
            session,
            plan.commands,
            done="would be imported" if session.dry_run else "imported",
            yes=yes,
            concurrency=concurrency,
            keep_going=keep_going,
            force=force,
            as_json=as_json,
            describe=lambda changed: (
                _created_as(session, changed) if "created" in changed.after else ""
            ),
            change=plan.change(),
            name="ImportIssues",
        )
    elif not plan.problems:
        output.info("Nothing to import.")
    if plan.problems:
        raise typer.Exit(1)


# What `issue edit --from-json` takes: Jira's own edit payload.
EDIT_TEMPLATE = {
    "fields": {"summary": "A new summary", "duedate": "2026-12-31"},
    "update": {
        "labels": [{"add": "triaged"}, {"remove": "needs-triage"}],
        "components": [{"set": [{"name": "API"}]}],
    },
}


def _edit_issue_text(session: Session, summary: str, description: str) -> tuple[str, str]:
    template = f"{summary}\n\n{description}\n" if summary or description else "\n\n"
    text = edit_text(
        template
        + "\n<!-- First line: the summary. Then a blank line and the description (Markdown). "
        "This comment is removed. -->\n",
        config=session.config,
    )
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip("\n")
    first, _, rest = text.partition("\n")
    return first.strip(), rest.strip()


# ── edit ─────────────────────────────────────────────────────────────────────


@app.command()
@guarded
def edit(
    keys: KeysArg = None,
    jql: JqlOpt = None,
    saved_filter: FilterOpt = None,
    from_file: FromFileOpt = None,
    summary: SummaryOpt = None,
    description: DescriptionOpt = None,
    description_file: DescriptionFileOpt = None,
    issue_type: TypeOpt = None,
    assignee: AssigneeOpt = None,
    reporter: ReporterOpt = None,
    priority: PriorityOpt = None,
    label: Annotated[
        list[str] | None, typer.Option("--label", "-L", help="Replace all labels with these.")
    ] = None,
    add_label: Annotated[
        list[str] | None, typer.Option("--add-label", help="Add labels, keeping the others.")
    ] = None,
    remove_label: Annotated[
        list[str] | None, typer.Option("--remove-label", help="Remove these labels.")
    ] = None,
    component: ComponentOpt = None,
    fix_version: FixVersionOpt = None,
    parent: ParentOpt = None,
    due: DueOpt = None,
    field: FieldOpt = None,
    editor: Annotated[
        bool,
        typer.Option("--editor", "-e", help="Edit the summary and description in $EDITOR."),
    ] = False,
    from_json: Annotated[
        Path | None,
        typer.Option("--from-json", help="Apply a Jira edit payload ({fields, update}) file."),
    ] = None,
    notify: Annotated[
        bool, typer.Option("--notify/--no-notify", help="Email watchers about the change.")
    ] = True,
    template: Annotated[
        bool, typer.Option("--template", help="Print an example --from-json file and exit.")
    ] = False,
    limit: BulkLimitOpt = None,
    concurrency: ConcurrencyOpt = CONCURRENCY,
    keep_going: KeepGoingOpt = False,
    force: ForceOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Change fields on one or many issues.

    Pick the issues by key, [bold]-[/] (stdin), [bold]--jql[/], [bold]--filter[/] or
    [bold]--from-file[/]. Shows what changes (each issue's value now and after, when one field
    changes), then asks once; [bold]--yes[/] skips the question. The fields' old values are
    kept in the audit log. Exits 0 when all were edited, 1 when some failed, 2 when nothing ran.

    [dim]acli-py issue edit DEMO-4 -s "New title" --add-label urgent
    acli-py issue edit --jql 'project = DEMO AND labels = old' --remove-label old -y[/]
    """
    if template:
        output.print_json(EDIT_TEMPLATE)
        return
    session = connect(dry_run)
    picked = pick_issues(session, keys, jql, saved_filter, from_file, limit=limit, force=force)
    if not picked:
        output.info("No issues match; nothing to edit.")
        return
    wanted = IssueInput(
        summary=summary,
        description=description_of(description, description_file),
        type=issue_type,
        reporter=reporter,
        priority=priority,
        labels=flat(label),
        components=flat(component),
        fix_versions=flat(fix_version),
        parent=parent,
        due=due,
        extra=list(field or []),
    )
    if editor:
        if len(picked) != 1:
            raise fail("--editor edits one issue at a time.")
        current = session.client.issue(picked[0], ["summary", "description"])["fields"]
        wanted.summary, wanted.description = _edit_issue_text(
            session, current.get("summary", ""), adf.to_text(current.get("description"))
        )
    fields = issue_fields.build(session.client, wanted, me=session.me)
    update: dict[str, list] = {}
    if from_json:
        extra = json.loads(from_json.read_text(encoding="utf-8"))
        fields.update(extra.get("fields", {}))
        update.update(extra.get("update", {}))
    label_ops = [{"add": v} for v in flat(add_label) or []]
    label_ops += [{"remove": v} for v in flat(remove_label) or []]
    if label_ops:
        update["labels"] = [*update.get("labels", []), *label_ops]
    if assignee is not None:
        fields["assignee"] = _assignee(session, assignee)
    if not fields and not update:
        raise fail("Nothing to change. See [bold]acli-py issue edit --help[/].")
    run_many(
        session,
        [EditIssue(key, fields, update, notify) for key in picked],
        done="would be edited" if session.dry_run else "edited",
        yes=yes,
        concurrency=concurrency,
        keep_going=keep_going,
        force=force,
        as_json=as_json,
    )


def _assignee(session: Session, who: str) -> dict | None:
    """Return the assignee field for `who`, with the name questions show (never sent)."""
    account = resolve.account_id(session.client, who, session.me)
    if account is None:
        return None
    return {"accountId": account, "displayName": who}


# ── assign ───────────────────────────────────────────────────────────────────


@app.command()
@guarded
def assign(
    keys: KeysArg = None,
    to: Annotated[
        str | None,
        typer.Option("--to", "-a", help="Email, account id, name, @me, or 'default'."),
    ] = None,
    unassign: Annotated[bool, typer.Option("--unassign", help="Remove the assignee.")] = False,
    jql: JqlOpt = None,
    saved_filter: FilterOpt = None,
    from_file: FromFileOpt = None,
    limit: BulkLimitOpt = None,
    concurrency: ConcurrencyOpt = CONCURRENCY,
    keep_going: KeepGoingOpt = False,
    force: ForceOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Assign issues to someone, to the project default, or to nobody.

    Shows each issue's assignee now and after, then asks once; [bold]--yes[/] skips the
    question. The previous assignees are kept in the audit log.

    [dim]acli-py issue assign DEMO-1 DEMO-2 --to @me
    acli-py issue assign --jql 'assignee = "old@example.com"' --to new@example.com -y[/]
    """
    if bool(to) == unassign:
        raise fail("Give exactly one of [bold]--to USER[/] and [bold]--unassign[/].")
    session = connect(dry_run)
    picked = pick_issues(session, keys, jql, saved_filter, from_file, limit=limit, force=force)
    if not picked:
        output.info("No issues match; nothing to assign.")
        return
    who = None if unassign else resolve.account_id(session.client, to or "", session.me)
    run_many(
        session,
        [AssignIssue(key, who, to or "") for key in picked],
        done=("would be " if session.dry_run else "") + ("unassigned" if unassign else "assigned"),
        yes=yes,
        concurrency=concurrency,
        keep_going=keep_going,
        force=force,
        as_json=as_json,
        describe=None if unassign else lambda changed: f"to {escape(to or '')}",
    )


# ── watch ────────────────────────────────────────────────────────────────────


def _watch(watch: bool, **kwargs: Any) -> None:
    """Make someone (you, by default) start or stop watching issues."""
    session = connect(kwargs["dry_run"])
    picked = pick_issues(
        session,
        kwargs["keys"],
        kwargs["jql"],
        kwargs["saved_filter"],
        kwargs["from_file"],
        limit=kwargs["limit"],
        force=kwargs["force"],
    )
    if not picked:
        output.info("No issues match; nothing to watch." if watch else "No issues match.")
        return
    user = kwargs["user"]
    account = resolve.user(session.client, user, session.me)["accountId"]
    name = "" if account == session.me else user
    done = ("now watched" if watch else "no longer watched") + (
        f" by {escape(name)}" if name else ""
    )
    run_many(
        session,
        [WatchIssue(key, account, watch, name) for key in picked],
        done=("would be " if session.dry_run else "") + done,
        yes=kwargs["yes"],
        concurrency=kwargs["concurrency"],
        keep_going=kwargs["keep_going"],
        force=kwargs["force"],
        as_json=kwargs["as_json"],
    )


UserOpt = Annotated[
    str, typer.Option("--user", "-u", help="Email, account id, name or @me (default).")
]


@app.command()
@guarded
def watch(
    keys: KeysArg = None,
    user: UserOpt = "@me",
    jql: JqlOpt = None,
    saved_filter: FilterOpt = None,
    from_file: FromFileOpt = None,
    limit: BulkLimitOpt = None,
    concurrency: ConcurrencyOpt = CONCURRENCY,
    keep_going: KeepGoingOpt = False,
    force: ForceOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Start watching issues (you, or someone else with [bold]--user[/]).

    [dim]acli-py issue watch DEMO-1 DEMO-2
    acli-py issue search '#web is:open' --output keys | acli-py issue watch - -u bob@example.com[/]
    """
    _watch(True, **locals())


@app.command()
@guarded
def unwatch(
    keys: KeysArg = None,
    user: UserOpt = "@me",
    jql: JqlOpt = None,
    saved_filter: FilterOpt = None,
    from_file: FromFileOpt = None,
    limit: BulkLimitOpt = None,
    concurrency: ConcurrencyOpt = CONCURRENCY,
    keep_going: KeepGoingOpt = False,
    force: ForceOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Stop watching issues (you, or someone else with [bold]--user[/]).

    [dim]acli-py issue unwatch --jql 'watcher = currentUser() AND statusCategory = Done' -y[/]
    """
    _watch(False, **locals())


# ── transition ───────────────────────────────────────────────────────────────


@app.command("transition")
@app.command("move", hidden=True)
@guarded
def transition(
    keys: KeysArg = None,
    to: Annotated[
        str | None,
        typer.Option("--to", "-s", help="Target status or transition name, e.g. 'In Progress'."),
    ] = None,
    comment: Annotated[
        str | None, typer.Option("--comment", "-m", help="Add this comment (Markdown).")
    ] = None,
    resolution: Annotated[
        str | None, typer.Option("--resolution", "-r", help="Set the resolution, e.g. Done.")
    ] = None,
    field: FieldOpt = None,
    jql: JqlOpt = None,
    saved_filter: FilterOpt = None,
    from_file: FromFileOpt = None,
    limit: BulkLimitOpt = None,
    concurrency: ConcurrencyOpt = CONCURRENCY,
    keep_going: KeepGoingOpt = False,
    force: ForceOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Move issues to another status (alias: move).

    Pick the issues by key, [bold]--jql[/] (JQL or a smart query), [bold]--filter[/] or
    [bold]--from-file[/]. Shows each issue's status now and after, then asks once;
    [bold]--yes[/] skips the question, and without a terminal to ask on it refuses unless
    given. Runs a few issues at a time and stops at the first failure unless
    [bold]--continue-on-error[/]. More than 200 issues needs [bold]--force[/]. The run is kept
    in the audit log. Exits 0 when all moved, 1 when some failed, 2 when nothing ran.

    [dim]acli-py issue transition DEMO-1 --to Done -m "Shipped in 2.4"
    acli-py issue move --jql 's:review sprint:open' --to Done --continue-on-error --yes[/]
    """
    if not to:
        raise fail(
            "Say where to: [bold]--to STATUS[/]. List options with "
            "[bold]acli-py issue transitions KEY[/]."
        )
    session = connect(dry_run)
    picked = pick_issues(session, keys, jql, saved_filter, from_file, limit=limit, force=force)
    if not picked:
        output.info("No issues match; nothing to move.")
        return
    extra = resolve.field_values(session.client, list(field or []), session.me)
    if resolution:
        extra["resolution"] = {"name": resolution}
    run_many(
        session,
        [TransitionIssue(key, to, comment or "", extra) for key in picked],
        done="would move" if session.dry_run else "moved",
        yes=yes,
        concurrency=concurrency,
        keep_going=keep_going,
        force=force,
        as_json=as_json,
        describe=lambda changed: f"to [bold]{escape(str(changed.after['status']))}[/]",
    )


@app.command()
@guarded
def transitions(
    key: Annotated[str, typer.Argument(help="Issue key.")],
    as_json: JsonOpt = False,
    out: OutputOpt = None,
) -> None:
    """List the statuses an issue can move to right now."""
    session = connect()
    output.emit(
        session.client.transitions(key.upper()),
        [
            Column("Id", lambda t: t.get("id"), style="dim"),
            Column("Transition", lambda t: t.get("name"), style="bold"),
            Column("To status", lambda t: dig(t, "to", "name")),
            Column("Category", lambda t: dig(t, "to", "statusCategory", "name"), style="dim"),
        ],
        fmt(as_json, chosen=out),
        empty="No transitions available.",
    )


# ── delete, archive, clone, open ─────────────────────────────────────────────


@app.command()
@guarded
def delete(
    keys: KeysArg = None,
    jql: JqlOpt = None,
    saved_filter: FilterOpt = None,
    from_file: FromFileOpt = None,
    subtasks: Annotated[
        bool, typer.Option("--with-subtasks", help="Also delete subtasks (else Jira refuses).")
    ] = False,
    limit: BulkLimitOpt = None,
    concurrency: ConcurrencyOpt = CONCURRENCY,
    keep_going: KeepGoingOpt = False,
    force: ForceOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Delete issues for good.

    Lists the issues first, then asks: for several, type how many to agree. [bold]--yes[/]
    skips the question; try [bold]--dry-run[/] to see which. What each issue was (summary,
    type, status) is kept in the audit log. Exits 0 when all were deleted, 1 when some failed,
    2 when nothing ran.

    [dim]acli-py issue delete DEMO-9
    acli-py issue search 'labels = spam' --output keys | acli-py issue delete - --yes[/]
    """
    session = connect(dry_run)
    picked = pick_issues(session, keys, jql, saved_filter, from_file, limit=limit, force=force)
    if not picked:
        output.info("No issues match; nothing to delete.")
        return
    run_many(
        session,
        [DeleteIssue(key, subtasks) for key in picked],
        done="would be deleted" if session.dry_run else "deleted",
        yes=yes,
        concurrency=concurrency,
        keep_going=keep_going,
        force=force,
        as_json=as_json,
    )


def _archive(archive: bool, **kwargs: Any) -> None:
    """Archive or restore issues."""
    session = connect(kwargs["dry_run"])
    picked = pick_issues(
        session,
        kwargs["keys"],
        kwargs.get("jql"),
        kwargs.get("saved_filter"),
        kwargs["from_file"],
        limit=kwargs["limit"],
        force=kwargs["force"],
    )
    if not picked:
        output.info("No issues match; nothing to archive." if archive else "No issues given.")
        return
    done = "archived" if archive else "unarchived"
    run_many(
        session,
        [ArchiveIssue(key, archive) for key in picked],
        done=("would be " if session.dry_run else "") + done,
        yes=kwargs["yes"],
        concurrency=kwargs["concurrency"],
        keep_going=kwargs["keep_going"],
        force=kwargs["force"],
        as_json=kwargs["as_json"],
    )


@app.command()
@guarded
def archive(
    keys: KeysArg = None,
    jql: JqlOpt = None,
    saved_filter: FilterOpt = None,
    from_file: FromFileOpt = None,
    limit: BulkLimitOpt = None,
    concurrency: ConcurrencyOpt = CONCURRENCY,
    keep_going: KeepGoingOpt = False,
    force: ForceOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Archive issues: hidden from boards and search, restorable later (Premium).

    Shows each issue's status, then asks once; [bold]--yes[/] skips the question.

    [dim]acli-py issue archive --jql 'project = DEMO AND resolved < -365d' --yes[/]
    """
    _archive(True, **locals())


@app.command()
@guarded
def unarchive(
    keys: KeysArg = None,
    from_file: FromFileOpt = None,
    limit: BulkLimitOpt = None,
    concurrency: ConcurrencyOpt = CONCURRENCY,
    keep_going: KeepGoingOpt = False,
    force: ForceOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Restore archived issues (by key: search doesn't find archived issues)."""
    _archive(False, **locals())


@app.command()
@guarded
def clone(
    keys: KeysArg = None,
    to_project: Annotated[
        str | None,
        typer.Option("--to-project", "-p", help="Clone into this project (default: same one)."),
    ] = None,
    prefix: Annotated[
        str, typer.Option("--prefix", help="Put this before each copied summary.")
    ] = "",
    link: Annotated[
        bool, typer.Option("--link/--no-link", help="Link each copy to its original.")
    ] = True,
    to_site: Annotated[
        str | None,
        typer.Option(
            "--to-site",
            help="Clone into another saved account's site (email@site or the site); "
            "needs --to-project.",
        ),
    ] = None,
    jql: JqlOpt = None,
    saved_filter: FilterOpt = None,
    from_file: FromFileOpt = None,
    limit: BulkLimitOpt = None,
    concurrency: ConcurrencyOpt = CONCURRENCY,
    keep_going: KeepGoingOpt = False,
    force: ForceOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Copy issues (summary, description, type, priority, labels…), in place or to a project.

    One issue is copied straight away; several are asked about once ([bold]--yes[/] skips
    it). With [bold]--to-site[/], copies go to another site you are logged in to, each with a
    web link back to its original. Each copy's key is kept in the audit log.

    [dim]acli-py issue clone DEMO-1 DEMO-2 --prefix "[copy] "
    acli-py issue clone --jql 'sprint = 7' --to-project OPS
    acli-py issue clone DEMO-1 --to-site me@other.atlassian.net --to-project NEW[/]
    """
    session = connect(dry_run)
    if to_site and not to_project:
        raise fail("--to-site needs --to-project: the other site has its own projects.")
    target = connect(dry_run, account_name=to_site) if to_site else session
    picked = pick_issues(session, keys, jql, saved_filter, from_file, limit=limit, force=force)
    if not picked:
        output.info("No issues match; nothing to clone.")
        return
    run_many(
        session,
        [CloneIssue(key, to_project or "", prefix, link) for key in picked],
        done="would be cloned" if session.dry_run else "cloned",
        yes=yes,
        concurrency=concurrency,
        keep_going=keep_going,
        force=force,
        as_json=as_json,
        describe=lambda changed: _created_as(session, changed),
        bus=session.bus_to(target),
    )


@app.command("open")
@guarded
def open_(key: Annotated[str, typer.Argument(help="Issue key.")]) -> None:
    """Open an issue in the browser."""
    open_url(connect().browse(key.upper()))
