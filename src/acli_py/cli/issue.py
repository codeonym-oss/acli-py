"""`acli-py issue`: view, search, create, edit, move, assign, clone, archive and delete issues."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

import typer
from rich.console import Group
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from acli_py import adf, output, resolve
from acli_py import fields as issue_fields
from acli_py.cli.common import (
    AllOpt,
    CsvOpt,
    DryRunOpt,
    FilterOpt,
    FromFileOpt,
    IgnoreErrorsOpt,
    JqlOpt,
    JsonOpt,
    KeysArg,
    LimitOpt,
    ProjectOpt,
    Session,
    WebOpt,
    YesOpt,
    confirm,
    connect,
    edit_text,
    fail,
    fmt,
    guarded,
    limit_of,
    open_url,
    plural,
    run_bulk,
)
from acli_py.client import API, DRY_RUN_ID
from acli_py.fields import IssueInput, flat, when
from acli_py.jql import JiraCatalog, compile_query, looks_like_jql
from acli_py.jql.catalog import spelling
from acli_py.jql.smart import cheatsheet
from acli_py.output import Column, Format, dig, status_text

app = typer.Typer(help="Work with issues (Jira's work items).", no_args_is_help=True)

VIEW_FIELDS = [
    "summary", "status", "issuetype", "priority", "assignee", "reporter", "labels",
    "components", "fixVersions", "parent", "duedate", "created", "updated", "resolution",
    "description", "subtasks", "issuelinks", "comment", "attachment",
]  # fmt: skip
LIST_FIELDS = ["issuetype", "status", "priority", "assignee", "summary"]

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
    """Show an issue: its details, description, subtasks, links and latest comments."""
    session = connect()
    key = key.upper()
    if web:
        open_url(session.browse(key))
        return
    extra = [f.strip() for f in (fields or "").split(",") if f.strip()]
    wanted = ["*all"] if "*all" in extra else [*VIEW_FIELDS, *extra]
    issue = session.client.issue(key, wanted, expand="names" if extra else None)
    if as_json:
        output.print_json(issue)
        return
    output.console.print(render_issue(session, issue, extra, comments))


def render_issue(session: Session, issue: dict, extra: list[str], comments: int) -> Group:
    """Return the rich rendering of one issue."""
    f = issue.get("fields", {})
    names = issue.get("names", {})
    rows: list[tuple[str, Any]] = [
        ("Type", escape(dig(f, "issuetype", "name", default=""))),
        ("Status", status_text(f.get("status"))),
        ("Priority", escape(dig(f, "priority", "name", default=""))),
        ("Assignee", escape(dig(f, "assignee", "displayName", default="")) or "[dim]unassigned[/]"),
        ("Reporter", escape(dig(f, "reporter", "displayName", default=""))),
        ("Parent", _issue_ref(f.get("parent"))),
        ("Labels", escape(", ".join(f.get("labels") or []))),
        ("Components", escape(issue_fields.text(f.get("components")))),
        ("Fix versions", escape(issue_fields.text(f.get("fixVersions")))),
        ("Resolution", escape(dig(f, "resolution", "name", default=""))),
        ("Due", f.get("duedate")),
        ("Created", when(f.get("created"))),
        ("Updated", when(f.get("updated"))),
    ]
    shown = {"description", "comment", "subtasks", "issuelinks", "attachment", "summary"}
    for field_id in extra if extra != ["*all"] else sorted(f):
        if field_id in shown or field_id == "*all" or field_id in dict(rows):
            continue
        value = issue_fields.text(f.get(field_id))
        if value:
            rows.append((escape(names.get(field_id, field_id)), escape(value)))
    parts: list[Any] = [
        output.details(
            f"{escape(issue['key'])}  {escape(f.get('summary', ''))}",
            [*rows, ("URL", f"[dim]{escape(session.browse(issue['key']))}[/]")],
        )
    ]
    description = adf.to_text(f.get("description"))
    if description:
        parts.append(Panel(Markdown(description), title="Description", title_align="left"))
    if subtasks := f.get("subtasks"):
        parts.append(Rule("Subtasks", align="left", style="dim"))
        parts.extend(
            f"  {escape(s['key'])}  {status_text(dig(s, 'fields', 'status'))}  "
            f"{escape(dig(s, 'fields', 'summary', default=''))}"
            for s in subtasks
        )
    if links := f.get("issuelinks"):
        parts.append(Rule("Links", align="left", style="dim"))
        parts.extend(f"  {line}" for line in (_link_line(link) for link in links))
    if attachments := f.get("attachment"):
        parts.append(Rule("Attachments", align="left", style="dim"))
        parts.extend(
            f"  [dim]{a['id']}[/]  {escape(a.get('filename', '?'))}  "
            f"[dim]{_size(a.get('size', 0))}[/]"
            for a in attachments
        )
    all_comments = dig(f, "comment", "comments", default=[])
    if comments and all_comments:
        total = dig(f, "comment", "total", default=len(all_comments))
        parts.append(Rule(f"Comments ({total})", align="left", style="dim"))
        for c in all_comments[-comments:]:
            author = dig(c, "author", "displayName", default="?")
            parts.append(
                f"[bold]{escape(author)}[/] [dim]{when(c.get('created'))} · id {c.get('id')}[/]"
            )
            parts.append(Markdown(adf.to_text(c.get("body")) or "_(empty)_"))
    return Group(*parts)


def _issue_ref(issue: dict | None) -> str:
    if not issue:
        return ""
    return f"{escape(issue['key'])} {escape(dig(issue, 'fields', 'summary', default=''))}"


def _link_line(link: dict) -> str:
    kind = link.get("type", {})
    if "outwardIssue" in link:
        phrase, other = kind.get("outward", "relates to"), link["outwardIssue"]
    else:
        phrase, other = kind.get("inward", "relates to"), link.get("inwardIssue", {})
    return (
        f"[dim]{phrase}[/] {escape(other.get('key', '?'))} "
        f"{status_text(dig(other, 'fields', 'status'))} "
        f"{escape(dig(other, 'fields', 'summary', default=''))} [dim](link {link.get('id')})[/]"
    )


def _size(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return str(size)


# ── search ───────────────────────────────────────────────────────────────────


def jql_quote(value: str) -> str:
    """Quote a value for JQL."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _in(field: str, values: list[str]) -> str:
    if len(values) == 1:
        return f"{field} = {jql_quote(values[0])}"
    return f"{field} in ({', '.join(jql_quote(v) for v in values)})"


def build_jql(
    session: Session,
    *,
    jql: str | None = None,
    project: str | None = None,
    assignee: str | None = None,
    status: list[str] | None = None,
    issue_type: list[str] | None = None,
    label: list[str] | None = None,
    text: str | None = None,
    open_only: bool = False,
    order: str | None = None,
) -> str:
    """Combine a JQL query and the shortcut options into one query."""
    clauses: list[str] = []
    ordering = ""
    if jql:
        body = jql
        if tail := _order_tail(jql):
            ordering, body = tail, jql[: len(jql) - len(tail)]
        if body.strip():
            clauses.append(f"({body.strip()})")
    if project:
        clauses.append(f"project = {jql_quote(project.upper())}")
    if assignee:
        who = assignee.strip().lower()
        if who in resolve.ME:
            clauses.append("assignee = currentUser()")
        elif who in resolve.NOBODY:
            clauses.append("assignee is EMPTY")
        else:
            clauses.append(
                f"assignee = {jql_quote(resolve.user(session.client, assignee)['accountId'])}"
            )
    if status := flat(status):
        clauses.append(_in("status", status))
    if issue_type := flat(issue_type):
        clauses.append(_in("issuetype", issue_type))
    if label := flat(label):
        clauses.append(_in("labels", label))
    if text:
        clauses.append(f"text ~ {jql_quote(text)}")
    if open_only:
        clauses.append("statusCategory != Done")
    if not clauses:
        default = session.config.defaults.get("project")
        if not default:
            raise fail(
                "Say what to search: a JQL query, or --project/--assignee/--status/--text…, "
                "or set a default with [bold]acli-py config set project KEY[/]."
            )
        clauses.append(f"project = {jql_quote(default)}")
    query = " AND ".join(clauses)
    if order:
        direction = "DESC" if order.startswith("-") else "ASC"
        name = order.lstrip("+-").strip()
        if " " in name:
            return f"{query} ORDER BY {name}"
        return f"{query} ORDER BY {name} {direction}"
    return f"{query} {ordering or 'ORDER BY updated DESC'}"


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


def _order_tail(jql: str) -> str:
    match = re.search(r"(?i)\border\s+by\b.*$", jql)
    return match.group(0) if match else ""


def issue_columns(session: Session, extra: list[str]) -> list[Column]:
    """Return the columns for issue lists: the defaults, or the fields asked for."""
    if extra:
        cols = [Column("Key", lambda i: i["key"], style="cyan", no_wrap=True)]
        for field_id in extra:
            if field_id == "key":
                continue
            cols.append(
                Column(
                    field_id,
                    lambda i, fid=field_id: issue_fields.text(dig(i, "fields", fid)),
                )
            )
        return cols
    return [
        Column("Key", lambda i: i["key"], style="cyan", no_wrap=True),
        Column("Type", lambda i: dig(i, "fields", "issuetype", "name"), no_wrap=True),
        Column("Status", lambda i: dig(i, "fields", "status", "name"), no_wrap=True),
        Column("Priority", lambda i: dig(i, "fields", "priority", "name"), no_wrap=True),
        Column("Assignee", lambda i: dig(i, "fields", "assignee", "displayName"), no_wrap=True),
        Column("Summary", lambda i: dig(i, "fields", "summary")),
    ]


@app.command("search")
@app.command("list", hidden=True)
@guarded
def search(
    jql: Annotated[
        str | None,
        typer.Argument(
            help="A smart query ('@me #web is:open', see --syntax) or JQL (optional).",
            show_default=False,
        ),
    ] = None,
    project: ProjectOpt = None,
    assignee: Annotated[
        str | None, typer.Option("--assignee", "-a", help="@me, 'none', email or name.")
    ] = None,
    status: Annotated[
        list[str] | None, typer.Option("--status", "-s", help="Status name (repeatable).")
    ] = None,
    issue_type: Annotated[
        list[str] | None, typer.Option("--type", "-t", help="Issue type (repeatable).")
    ] = None,
    label: Annotated[
        list[str] | None, typer.Option("--label", "-L", help="Label (repeatable).")
    ] = None,
    text: Annotated[str | None, typer.Option("--text", "-T", help="Full-text search.")] = None,
    open_only: Annotated[
        bool, typer.Option("--open", "-o", help="Only issues not done yet.")
    ] = False,
    saved_filter: Annotated[
        str | None, typer.Option("--filter", help="Use a saved filter's JQL (by id).")
    ] = None,
    order: Annotated[
        str | None,
        typer.Option("--order", help="Sort field; prefix '-' for descending, e.g. -created."),
    ] = None,
    fields: Annotated[
        str | None,
        typer.Option("--fields", help="Columns to show, comma-separated field ids."),
    ] = None,
    limit: LimitOpt = 50,
    all_pages: AllOpt = False,
    count: Annotated[bool, typer.Option("--count", help="Only print how many match.")] = False,
    web: WebOpt = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    syntax: Annotated[
        bool, typer.Option("--syntax", help="Show the smart query syntax and exit.")
    ] = False,
    raw: Annotated[
        bool, typer.Option("--raw", help="Send the query as JQL, never as a smart query.")
    ] = False,
) -> None:
    """Find issues with a smart query, JQL, and/or simple options.

    [dim]acli-py issue search '@me is:open #web sort:-priority'
    acli-py issue search 'p:DEMO s:progress updated:7d "login"'
    acli-py issue search -p DEMO -a @me --open
    acli-py issue search 'project = DEMO AND sprint in openSprints()' --csv[/]
    """
    if syntax:
        show_syntax()
        return
    session = connect()
    if jql and not raw and not looks_like_jql(jql):
        compiled = compile_query(
            jql, resolve=spelling(JiraCatalog(session.client)), default_order=""
        )
        for warning in compiled.warnings:
            output.warn(escape(warning))
        jql = compiled.jql
    base = session.client.filter(saved_filter)["jql"] if saved_filter else None
    query_text = " AND ".join(f"({q})" for q in (base, jql) if q) if base and jql else base or jql
    query = build_jql(
        session,
        jql=query_text,
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
        number = session.client.count(query)
        if as_json:
            output.print_json({"jql": query, "count": number})
        else:
            output.console.print(number)
        return
    extra = [f.strip() for f in (fields or "").split(",") if f.strip()]
    with output.errors.status("Searching…"):
        issues = list(
            session.client.search(query, extra or LIST_FIELDS, limit=limit_of(limit, all_pages))
        )
    output.emit(
        issues, issue_columns(session, extra), fmt(as_json, as_csv), empty="No issues match."
    )
    if fmt(as_json, as_csv) is Format.table and issues:
        more = "" if all_pages or len(issues) < limit else " (use --all for every page)"
        output.info(f"{plural(len(issues), 'issue')}{more} · [dim]{escape(query)}[/]")


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
        typer.Option("--from-json", help="Create from a JSON file: one issue or a list."),
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
    ignore_errors: IgnoreErrorsOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Create an issue, or many from a JSON/CSV file.

    Options given on the command line fill in what each file row leaves out.

    [dim]acli-py issue create -p DEMO -t Bug -s "Login fails on Safari" -a @me -L web
    acli-py issue create --from-csv backlog.csv -p DEMO --dry-run[/]
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
        _create_many(session, rows, common, yes, ignore_errors, as_json)
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
    created = _create_one(session, common)
    if as_json:
        output.print_json(created)
    key = created.get("key", "?")
    if session.dry_run:
        output.info("Would create the issue above.")
        return
    output.success(f"Created [bold cyan]{escape(key)}[/]  {escape(session.browse(key))}")
    if web:
        open_url(session.browse(key))


def _defaults(session: Session, wanted: IssueInput) -> IssueInput:
    if not wanted.raw:
        wanted.project = session.project(wanted.project)
        wanted.type = wanted.type or session.config.defaults.get("issue-type") or "Task"
    return wanted


def _create_one(session: Session, wanted: IssueInput, catalog: Any = None) -> dict:
    wanted = _defaults(session, wanted)
    body: dict[str, Any] = {
        "fields": issue_fields.build(
            session.client, wanted, me=session.me, creating=True, catalog=catalog
        )
    }
    if wanted.raw.get("update"):
        body["update"] = wanted.raw["update"]
    return session.client.post(f"{API}/issue", body)


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


def _create_many(
    session: Session,
    rows: list[dict],
    common: IssueInput,
    yes: bool,
    ignore_errors: bool,
    as_json: bool,
) -> None:
    if not rows:
        raise fail("The file holds no issues.")
    wanted = [_merge(IssueInput.from_mapping(row), common) for row in rows]
    for n, item in enumerate(wanted, 1):
        if not item.raw and not item.summary:
            raise fail(f"Row {n} has no summary.")
    confirm(f"Create {plural(len(wanted), 'issue')}?", yes, session)
    catalog = resolve.FieldCatalog.load(session.client) if any(w.extra for w in wanted) else None
    labels = {f"#{n}": w for n, w in enumerate(wanted, 1)}

    def one(label: str) -> dict:
        return _create_one(session, labels[label], catalog)

    run_bulk(
        list(labels),
        one,
        done="would be created" if session.dry_run else "created",
        ignore_errors=ignore_errors,
        as_json=as_json,
        describe=lambda label, r: (
            escape(labels[label].summary or dig(labels[label].raw, "fields", "summary", default=""))
            if r.get("key") == DRY_RUN_ID
            else f"as [bold cyan]{escape(r.get('key', '?'))}[/]"
        ),
    )


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
    yes: YesOpt = False,
    ignore_errors: IgnoreErrorsOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Change fields on one or many issues.

    [dim]acli-py issue edit DEMO-4 -s "New title" --add-label urgent
    acli-py issue edit --jql 'project = DEMO AND labels = old' --remove-label old -y[/]
    """
    if template:
        output.print_json(EDIT_TEMPLATE)
        return
    session = connect(dry_run)
    picked = resolve.targets(session.client, keys, jql, saved_filter, from_file)
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
    payload: dict[str, Any] = {"fields": issue_fields.build(session.client, wanted, me=session.me)}
    if from_json:
        extra = json.loads(from_json.read_text(encoding="utf-8"))
        payload["fields"].update(extra.get("fields", {}))
        payload["update"] = extra.get("update", {})
    updates = payload.setdefault("update", {})
    label_ops = [{"add": v} for v in flat(add_label) or []]
    label_ops += [{"remove": v} for v in flat(remove_label) or []]
    if label_ops:
        updates["labels"] = [*updates.get("labels", []), *label_ops]
    if not updates:
        del payload["update"]
    assign_to = (
        resolve.account_id(session.client, assignee, session.me) if assignee is not None else ...
    )
    if not payload.get("fields") and "update" not in payload and assign_to is ...:
        raise fail("Nothing to change. See [bold]acli-py issue edit --help[/].")
    if len(picked) > 1:
        confirm(f"Edit {plural(len(picked), 'issue')}?", yes, session)

    def one(key: str) -> None:
        if payload.get("fields") or "update" in payload:
            session.client.put(
                f"{API}/issue/{key}", payload, notifyUsers=None if notify else "false"
            )
        if assign_to is not ...:
            session.client.put(f"{API}/issue/{key}/assignee", {"accountId": assign_to})

    run_bulk(
        picked,
        one,
        done="would be edited" if session.dry_run else "edited",
        ignore_errors=ignore_errors,
        as_json=as_json,
    )


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
    yes: YesOpt = False,
    ignore_errors: IgnoreErrorsOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Assign issues to someone, to the project default, or to nobody.

    [dim]acli-py issue assign DEMO-1 DEMO-2 --to @me
    acli-py issue assign --jql 'assignee = "old@example.com"' --to new@example.com -y[/]
    """
    if bool(to) == unassign:
        raise fail("Give exactly one of [bold]--to USER[/] and [bold]--unassign[/].")
    session = connect(dry_run)
    picked = resolve.targets(session.client, keys, jql, saved_filter, from_file)
    who = None if unassign else resolve.account_id(session.client, to or "", session.me)
    if len(picked) > 1:
        confirm(f"Assign {plural(len(picked), 'issue')}?", yes, session)
    run_bulk(
        picked,
        lambda key: session.client.put(f"{API}/issue/{key}/assignee", {"accountId": who}),
        done=("would be " if session.dry_run else "")
        + ("unassigned" if unassign else f"assigned to {escape(to or '')}"),
        ignore_errors=ignore_errors,
        as_json=as_json,
    )


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
    yes: YesOpt = False,
    ignore_errors: IgnoreErrorsOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Move issues to another status (alias: move).

    [dim]acli-py issue transition DEMO-1 --to Done -m "Shipped in 2.4"[/]
    """
    if not to:
        raise fail(
            "Say where to: [bold]--to STATUS[/]. List options with "
            "[bold]acli-py issue transitions KEY[/]."
        )
    session = connect(dry_run)
    picked = resolve.targets(session.client, keys, jql, saved_filter, from_file)
    extra = resolve.field_values(session.client, list(field or []), session.me)
    if resolution:
        extra["resolution"] = {"name": resolution}
    if len(picked) > 1:
        confirm(f"Move {plural(len(picked), 'issue')} to {to}?", yes, session)

    def one(key: str) -> str:
        chosen = resolve.transition(session.client, key, to)
        body: dict[str, Any] = {"transition": {"id": chosen["id"]}}
        if extra:
            body["fields"] = extra
        if comment:
            body["update"] = {"comment": [{"add": {"body": adf.to_adf(comment)}}]}
        session.client.post(f"{API}/issue/{key}/transitions", body)
        return dig(chosen, "to", "name", default=chosen.get("name", to))

    run_bulk(
        picked,
        one,
        done="would move" if session.dry_run else "moved",
        ignore_errors=ignore_errors,
        as_json=as_json,
        describe=lambda _key, target: f"to [bold]{escape(target)}[/]",
    )


@app.command()
@guarded
def transitions(
    key: Annotated[str, typer.Argument(help="Issue key.")],
    as_json: JsonOpt = False,
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
        fmt(as_json),
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
    yes: YesOpt = False,
    ignore_errors: IgnoreErrorsOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Delete issues for good. Asks first; try --dry-run to see which."""
    session = connect(dry_run)
    picked = resolve.targets(session.client, keys, jql, saved_filter, from_file)
    confirm(
        f"Permanently delete {plural(len(picked), 'issue')} ({', '.join(picked[:5])}"
        f"{'…' if len(picked) > 5 else ''})?",
        yes,
        session,
    )
    run_bulk(
        picked,
        lambda key: session.client.delete(
            f"{API}/issue/{key}", deleteSubtasks="true" if subtasks else None
        ),
        done="would be deleted" if session.dry_run else "deleted",
        ignore_errors=ignore_errors,
        as_json=as_json,
    )


def _archive(unarchive: bool, **kwargs: Any) -> None:
    session = connect(kwargs["dry_run"])
    picked = resolve.targets(
        session.client, kwargs["keys"], kwargs.get("jql"), kwargs.get("saved_filter"),
        kwargs["from_file"],
    )  # fmt: skip
    verb = "Unarchive" if unarchive else "Archive"
    confirm(f"{verb} {plural(len(picked), 'issue')}?", kwargs["yes"], session)
    path = f"{API}/issue/{'unarchive' if unarchive else 'archive'}"
    done = f"{verb.lower()}d"
    results: list[dict] = []
    # The archive endpoints take up to 1000 issues per call. Without --ignore-errors, a batch
    # with failures stops the batches after it.
    for start in range(0, len(picked), 1000):
        if results and results[-1].get("errors") and not kwargs["ignore_errors"]:
            output.info(f"{plural(len(picked) - start, 'issue')} not tried.")
            break
        batch = picked[start : start + 1000]
        result = session.client.put(path, {"issueIdsOrKeys": batch}) or {}
        results.append(result)
        failed = {
            key
            for error in (result.get("errors") or {}).values()
            for key in error.get("issueIdsOrKeys", [])
        }
        for key in batch:
            if key in failed:
                output.error(f"{key} could not be {done}")
            else:
                output.success(f"{key} {'would be ' if session.dry_run else ''}{done}")
    if kwargs["as_json"]:
        output.print_json(results)
    if any(r.get("errors") for r in results):
        raise typer.Exit(1)


@app.command()
@guarded
def archive(
    keys: KeysArg = None,
    jql: JqlOpt = None,
    saved_filter: FilterOpt = None,
    from_file: FromFileOpt = None,
    yes: YesOpt = False,
    ignore_errors: IgnoreErrorsOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Archive issues: hidden from boards and search, restorable later (Premium)."""
    _archive(False, **locals())


@app.command()
@guarded
def unarchive(
    keys: KeysArg = None,
    from_file: FromFileOpt = None,
    yes: YesOpt = False,
    ignore_errors: IgnoreErrorsOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Restore archived issues."""
    _archive(True, **locals())


CLONE_FIELDS = [
    "summary", "description", "issuetype", "priority", "labels", "components", "duedate",
    "environment", "parent", "project", "fixVersions",
]  # fmt: skip


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
    yes: YesOpt = False,
    ignore_errors: IgnoreErrorsOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Copy issues (summary, description, type, priority, labels…), in place or to a project.

    With [bold]--to-site[/], copies go to another site you are logged in to, each with a web
    link back to its original.

    [dim]acli-py issue clone DEMO-1 DEMO-2 --prefix "[copy] "
    acli-py issue clone --jql 'sprint = 7' --to-project OPS
    acli-py issue clone DEMO-1 --to-site me@other.atlassian.net --to-project NEW[/]
    """
    session = connect(dry_run)
    if to_site and not to_project:
        raise fail("--to-site needs --to-project: the other site has its own projects.")
    target = connect(dry_run, account_name=to_site) if to_site else session
    cross_site = target.url != session.url
    picked = resolve.targets(session.client, keys, jql, saved_filter, from_file)
    if len(picked) > 1:
        confirm(f"Clone {plural(len(picked), 'issue')}?", yes, session)
    cloners = None
    if link and not cross_site:
        cloners = next(
            (t for t in session.client.link_types() if t.get("name", "").lower() == "cloners"),
            None,
        )

    def one(key: str) -> dict:
        original = session.client.issue(key, CLONE_FIELDS)
        f = original["fields"]
        same_project = not cross_site and (
            not to_project or to_project.upper() == f["project"]["key"]
        )
        new: dict[str, Any] = {
            "project": {"key": (to_project or f["project"]["key"]).upper()},
            "summary": prefix + f.get("summary", ""),
            "issuetype": {"name": f["issuetype"]["name"]},
        }
        for name in ("description", "labels", "duedate", "environment"):
            if f.get(name):
                new[name] = f[name]
        if f.get("priority"):
            new["priority"] = {"name": f["priority"]["name"]}
        if same_project:
            if f.get("components"):
                new["components"] = [{"id": c["id"]} for c in f["components"]]
            if f.get("fixVersions"):
                new["fixVersions"] = [{"id": v["id"]} for v in f["fixVersions"]]
            if f.get("parent"):
                new["parent"] = {"key": f["parent"]["key"]}
        created = target.client.post(f"{API}/issue", {"fields": new})
        if cross_site and link:
            target.client.post(
                f"{API}/issue/{created['key']}/remotelink",
                {"object": {"url": session.browse(key), "title": f"Cloned from {key}"}},
            )
        elif cloners:
            # The outward ("from") issue is the copy: "DEMO-9 clones DEMO-1".
            session.client.post(
                f"{API}/issueLink",
                {
                    "type": {"name": cloners["name"]},
                    "outwardIssue": {"key": created["key"]},
                    "inwardIssue": {"key": key},
                },
            )
        return created

    run_bulk(
        picked,
        one,
        done="would be cloned" if session.dry_run else "cloned",
        ignore_errors=ignore_errors,
        as_json=as_json,
        describe=lambda _k, r: "" if r.get("dryRun") else f"as [bold cyan]{escape(r['key'])}[/]",
    )


@app.command("open")
@guarded
def open_(key: Annotated[str, typer.Argument(help="Issue key.")]) -> None:
    """Open an issue in the browser."""
    open_url(connect().browse(key.upper()))
