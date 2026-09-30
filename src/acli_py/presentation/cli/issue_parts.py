"""The parts of an issue: comments, links, attachments, watchers and worklogs.

Every command here sends messages on the bus: queries to read, commands to change (they ask
first, run over many issues or items through the bulk engine, and land in the audit log).
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.markdown import Markdown
from rich.markup import escape

from acli_py.application.commands.attach_file.command import AttachFile
from acli_py.application.commands.comment_on_issue.command import CommentOnIssue
from acli_py.application.commands.delete_attachment.command import DeleteAttachment
from acli_py.application.commands.delete_comment.command import DeleteComment
from acli_py.application.commands.delete_worklog.command import DeleteWorklog
from acli_py.application.commands.edit_comment.command import EditComment
from acli_py.application.commands.link_issues.command import LinkIssues
from acli_py.application.commands.log_work.command import LogWork
from acli_py.application.commands.unlink_issues.command import UnlinkIssues
from acli_py.application.commands.watch_issue.command import WatchIssue
from acli_py.application.queries.download_attachment.query import DownloadAttachment
from acli_py.application.queries.get_comment.query import GetComment
from acli_py.application.queries.list_attachments.query import ListAttachments
from acli_py.application.queries.list_audiences.query import ListAudiences
from acli_py.application.queries.list_comments.query import ListComments
from acli_py.application.queries.list_link_types.query import ListLinkTypes
from acli_py.application.queries.list_links.query import ListLinks
from acli_py.application.queries.list_watchers.query import ListWatchers
from acli_py.application.queries.list_worklogs.query import ListWorklogs
from acli_py.domain.issue import Audience, is_duration, looks_like_key
from acli_py.domain.values import when
from acli_py.presentation import output
from acli_py.presentation.cli.common import (
    AllOpt,
    BulkLimitOpt,
    ConcurrencyOpt,
    DryRunOpt,
    FilterOpt,
    ForceOpt,
    FromFileOpt,
    JqlOpt,
    JsonOpt,
    KeepGoingOpt,
    KeysArg,
    LimitOpt,
    OutputOpt,
    YesOpt,
    connect,
    edit_text,
    fail,
    fmt,
    guarded,
    limit_of,
    pick_issues,
    read_text,
    run_many,
)
from acli_py.presentation.output import Column, dig

KeyArg = Annotated[str, typer.Argument(help="Issue key, e.g. DEMO-12.")]


def _ids(values: list[str] | None) -> list[str]:
    """Return ids given as separate words, or joined with commas or spaces."""
    return [i for value in values or [] for i in re.split(r"[\s,]+", value) if i]


def _audience(role: str | None, group: str | None) -> Audience | None:
    if role and group:
        raise fail("Restrict a comment to a role or a group, not both.")
    if role:
        return Audience("role", role)
    if group:
        return Audience("group", group)
    return None


# ── comments ─────────────────────────────────────────────────────────────────

comment_app = typer.Typer(help="Read, add, edit and delete comments.", no_args_is_help=True)

BodyOpt = Annotated[
    str | None, typer.Option("--body", "-b", help="Markdown (or ADF JSON); '-' reads stdin.")
]
BodyFileOpt = Annotated[
    Path | None,
    typer.Option(
        "--body-file",
        "-B",
        "--body-adf",
        help="Read the body from a file: Markdown, or ADF JSON ('-' for stdin).",
    ),
]
EditorOpt = Annotated[bool, typer.Option("--editor", "-e", help="Write the body in $EDITOR.")]
RoleOpt = Annotated[str | None, typer.Option("--role", help="Only this project role can see it.")]
GroupOpt = Annotated[str | None, typer.Option("--group", help="Only this group can see it.")]


def _body(session: Any, body: str | None, body_file: Path | None, editor: bool) -> str:
    text = read_text(body, body_file)
    if editor:
        text = edit_text(text or "", config=session.config)
    if not text or not text.strip():
        raise fail("The comment is empty: pass [bold]-b TEXT[/], [bold]-B FILE[/] or --editor.")
    return text


@comment_app.command("list")
@guarded
def comment_list(
    key: KeyArg,
    newest_first: Annotated[
        bool, typer.Option("--newest-first", help="Show the latest comment first.")
    ] = False,
    limit: LimitOpt = 50,
    all_pages: AllOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Show an issue's comments, oldest first."""
    session = connect()
    view = session.send(ListComments(key, newest_first, limit_of(limit, all_pages)))
    if as_json:
        output.print_json(view.to_json())
        return
    if not view.comments:
        output.info(f"{view.key} has no comments.")
    for c in view.comments:
        author = c.author.name if c.author else "?"
        output.console.print(
            f"[bold]{escape(author)}[/] [dim]{when(c.created)} · id {c.id}"
            + (f" · edited {when(c.updated)}" if c.updated else "")
            + (f" · visible to {escape(c.visible_to)}" if c.visible_to else "")
            + "[/]"
        )
        output.console.print(Markdown(c.body or "_(empty)_"))
        output.console.print()


@comment_app.command("add")
@guarded
def comment_add(
    keys: KeysArg = None,
    body: BodyOpt = None,
    body_file: BodyFileOpt = None,
    editor: EditorOpt = False,
    role: RoleOpt = None,
    group: GroupOpt = None,
    edit_last: Annotated[
        bool, typer.Option("--edit-last", help="Replace your latest comment instead.")
    ] = False,
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
    """Comment on one or many issues.

    [dim]acli-py issue comment add DEMO-3 -b "Fixed in **2.4**"
    echo "Deployed" | acli-py issue comment add --jql 'fixVersion = 2.4' -b - -y[/]
    """
    session = connect(dry_run)
    audience = _audience(role, group)
    text = _body(session, body, body_file, editor)
    picked = pick_issues(session, keys, jql, saved_filter, from_file, limit=limit, force=force)
    replacing = session.me if edit_last else ""
    run_many(
        session,
        [CommentOnIssue(k, text, audience, replacing) for k in picked],
        done="would get the comment" if session.dry_run else "commented",
        yes=yes,
        concurrency=concurrency,
        keep_going=keep_going,
        force=force,
        as_json=as_json,
        describe=lambda r: "" if session.dry_run else f"[dim](id {r.after.get('comment')})[/]",
    )


@comment_app.command("edit")
@guarded
def comment_edit(
    key: KeyArg,
    comment_id: Annotated[str, typer.Argument(help="Comment id (see `comment list`).")],
    body: BodyOpt = None,
    body_file: BodyFileOpt = None,
    editor: EditorOpt = False,
    role: RoleOpt = None,
    group: GroupOpt = None,
    notify: Annotated[
        bool, typer.Option("--notify/--no-notify", help="Email watchers about the change.")
    ] = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Replace a comment's text."""
    session = connect(dry_run)
    audience = _audience(role, group)
    if editor and body is None and body_file is None:
        body = session.send(GetComment(key, comment_id)).body
    text = _body(session, body, body_file, editor)
    run_many(
        session,
        [EditComment(key, comment_id, text, audience, notify)],
        done="would be edited" if session.dry_run else "edited",
        yes=yes,
    )


@comment_app.command("delete")
@guarded
def comment_delete(
    key: KeyArg,
    comment_ids: Annotated[list[str], typer.Argument(help="Comment ids.")],
    keep_going: KeepGoingOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Delete comments."""
    session = connect(dry_run)
    run_many(
        session,
        [DeleteComment(key, cid) for cid in _ids(comment_ids)],
        done="would be deleted" if session.dry_run else "deleted",
        yes=yes,
        keep_going=keep_going,
        concurrency=1,
    )


@comment_app.command("visibility")
@guarded
def comment_visibility(
    project: Annotated[
        str | None, typer.Option("--project", "-p", help="Show this project's roles.")
    ] = None,
    as_json: JsonOpt = False,
    out: OutputOpt = None,
) -> None:
    """List the roles (with --project) or groups a comment can be restricted to."""
    session = connect()
    rows = session.send(ListAudiences(project or "")).to_json()
    columns = [
        Column("Type", lambda r: r["type"], style="dim"),
        Column("Name", lambda r: r["name"]),
    ]
    output.emit(rows, columns, fmt(as_json, chosen=out))


# ── links ────────────────────────────────────────────────────────────────────

link_app = typer.Typer(help="Link issues to each other.", no_args_is_help=True)


def _link_rows(from_json: Path | None, from_csv: Path | None) -> list[tuple[str, str, str]]:
    triples: list[tuple[str, str, str]] = []
    if from_json:
        triples += [
            (str(r["from"]), str(r["type"]), str(r["to"]))
            for r in json.loads(from_json.read_text(encoding="utf-8"))
        ]
    if from_csv:
        rows = list(csv.reader(from_csv.read_text(encoding="utf-8-sig").splitlines()))
        triples += [(r[0], r[1], r[2]) for r in rows[1:] if len(r) >= 3]
    return triples


@link_app.command("add")
@guarded
def link_add(
    words: Annotated[
        list[str] | None,
        typer.Argument(
            help="FROM TYPE TO, read as a sentence (TYPE: blocks, 'is blocked by', relates to, "
            "Duplicate…). With --jql, --filter or FROM '-', each issue found is FROM.",
            show_default=False,
        ),
    ] = None,
    from_json: Annotated[
        Path | None,
        typer.Option(
            "--from-json", help='Many links: [{"from": "A-1", "type": "blocks", "to": "A-2"}].'
        ),
    ] = None,
    from_csv: Annotated[
        Path | None, typer.Option("--from-csv", help="Many links: CSV with from,type,to columns.")
    ] = None,
    comment: Annotated[
        str | None, typer.Option("--comment", "-m", help="Also comment on the first issue.")
    ] = None,
    template: Annotated[
        bool, typer.Option("--template", help="Print an example --from-json file and exit.")
    ] = False,
    jql: JqlOpt = None,
    saved_filter: FilterOpt = None,
    limit: BulkLimitOpt = None,
    concurrency: ConcurrencyOpt = 4,
    keep_going: KeepGoingOpt = False,
    force: ForceOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Link issues, read as a sentence.

    [dim]acli-py issue link add DEMO-1 blocks DEMO-2
    acli-py issue link add DEMO-5 "is duplicated by" DEMO-9
    acli-py issue link add --jql 'labels = login' "relates to" DEMO-1[/]
    """
    if template:
        output.print_json(
            [
                {"from": "DEMO-1", "type": "blocks", "to": "DEMO-2"},
                {"from": "DEMO-3", "type": "is duplicated by", "to": "DEMO-4"},
            ]
        )
        return
    words = words or []
    session = connect(dry_run)
    triples = _link_rows(from_json, from_csv)
    if len(words) == 3 and words[0] != "-" and not (jql or saved_filter):
        triples.append((words[0], words[1], words[2]))
    elif len(words) in (2, 3) and (jql or saved_filter or words[0] == "-"):
        kind, target = words[-2:]
        sources = pick_issues(
            session, words[:1] if len(words) == 3 else None, jql, saved_filter,
            limit=limit, force=force,
        )  # fmt: skip
        triples += [(source, kind, target) for source in sources]
    elif words:
        raise fail("Give three words: [bold]acli-py issue link add FROM TYPE TO[/].")
    if not triples:
        raise fail("Nothing to link. See [bold]acli-py issue link add --help[/].")
    run_many(
        session,
        [LinkIssues(a, k, b, comment or "") for a, k, b in triples],
        done="would be linked" if session.dry_run else "linked",
        yes=yes,
        concurrency=concurrency,
        keep_going=keep_going,
        force=force,
        as_json=as_json,
    )


@link_app.command("list")
@guarded
def link_list(key: KeyArg, as_json: JsonOpt = False, out: OutputOpt = None) -> None:
    """Show an issue's links (`--output keys` prints the linked issues, for a pipe)."""
    session = connect()
    view = session.send(ListLinks(key))
    output.emit(
        view.to_json(),
        [
            Column("Link id", lambda r: r["id"], style="dim"),
            Column("Relation", lambda r: r["phrase"]),
            Column("Issue", lambda r: r["key"], style="cyan"),
            Column("Status", lambda r: r["status"]),
            Column("Summary", lambda r: r["summary"]),
        ],
        fmt(as_json, chosen=out),
        empty=f"{view.key} has no links.",
    )


@link_app.command("delete")
@guarded
def link_delete(
    link_ids: Annotated[
        list[str] | None, typer.Argument(help="Link ids (see `link list`).")
    ] = None,
    from_json: Annotated[
        Path | None, typer.Option("--from-json", help='A JSON list of ids, or [{"id": …}].')
    ] = None,
    from_csv: Annotated[
        Path | None, typer.Option("--from-csv", help="A CSV whose first column holds link ids.")
    ] = None,
    keep_going: KeepGoingOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Remove links between issues."""
    ids = _ids(link_ids)
    if from_json:
        ids += [
            str(v["id"] if isinstance(v, dict) else v) for v in json.loads(from_json.read_text())
        ]
    if from_csv:
        rows = list(csv.reader(from_csv.read_text(encoding="utf-8-sig").splitlines()))
        ids += [r[0] for r in rows if r and r[0].strip().isdigit()]
    if not ids:
        raise fail("Which links? Give ids; [bold]acli-py issue link list KEY[/] shows them.")
    session = connect(dry_run)
    run_many(
        session,
        [UnlinkIssues(i) for i in ids],
        done="would be deleted" if session.dry_run else "deleted",
        yes=yes,
        keep_going=keep_going,
    )


@link_app.command("types")
@guarded
def link_types(as_json: JsonOpt = False, out: OutputOpt = None) -> None:
    """List the kinds of link the site offers."""
    session = connect()
    output.emit(
        session.send(ListLinkTypes()).to_json(),
        [
            Column("Id", lambda t: t["id"], style="dim"),
            Column("Name", lambda t: t["name"], style="bold"),
            Column("Outward (A … B)", lambda t: t["outward"]),
            Column("Inward (B … A)", lambda t: t["inward"]),
        ],
        fmt(as_json, chosen=out),
    )


# ── attachments ──────────────────────────────────────────────────────────────

attachment_app = typer.Typer(
    help="List, upload, download and delete attachments.", no_args_is_help=True
)


@attachment_app.command("list")
@guarded
def attachment_list(key: KeyArg, as_json: JsonOpt = False, out: OutputOpt = None) -> None:
    """Show an issue's attachments."""
    session = connect()
    view = session.send(ListAttachments(key))
    output.emit(
        view.to_json(),
        [
            Column("Id", lambda a: a["id"], style="dim"),
            Column("File", lambda a: a["filename"], style="bold"),
            Column("Size", lambda a: f"{a['size']:,} B", justify="right"),
            Column("Type", lambda a: a["mimeType"], style="dim"),
            Column("By", lambda a: dig(a, "author", "name")),
            Column("Added", lambda a: when(a["created"])),
        ],
        fmt(as_json, chosen=out),
        empty=f"{view.key} has no attachments.",
    )


@attachment_app.command("upload")
@guarded
def attachment_upload(
    key: KeyArg,
    files: Annotated[
        list[Path], typer.Argument(help="Files to attach.", exists=True, dir_okay=False)
    ],
    keep_going: KeepGoingOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Attach files to an issue."""
    session = connect(dry_run)
    verb = "Would attach" if session.dry_run else "Attached"
    run_many(
        session,
        [AttachFile(key, path) for path in files],
        done="attached",
        yes=yes,
        keep_going=keep_going,
        concurrency=1,
        as_json=as_json,
        line=lambda r: f"{verb} {escape(r.after['file'])} to {r.key}",
    )


@attachment_app.command("download")
@guarded
def attachment_download(
    attachment_ids: Annotated[list[str], typer.Argument(help="Attachment ids (see `list`).")],
    out: Annotated[
        Path, typer.Option("--out", "-o", help="Directory to save into.", file_okay=False)
    ] = Path(),
) -> None:
    """Download attachments by id."""
    session = connect()
    out.mkdir(parents=True, exist_ok=True)
    for attachment_id in _ids(attachment_ids):
        saved = session.send(DownloadAttachment(attachment_id, out))
        output.success(f"Saved {escape(str(saved.path))} ({saved.size:,} bytes)")


@attachment_app.command("delete")
@guarded
def attachment_delete(
    attachment_ids: Annotated[list[str], typer.Argument(help="Attachment ids.")],
    keep_going: KeepGoingOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Delete attachments by id."""
    session = connect(dry_run)
    run_many(
        session,
        [DeleteAttachment(i) for i in _ids(attachment_ids)],
        done="would be deleted" if session.dry_run else "deleted",
        yes=yes,
        keep_going=keep_going,
    )


# ── watchers ─────────────────────────────────────────────────────────────────

watcher_app = typer.Typer(help="See, add and remove watchers.", no_args_is_help=True)


@watcher_app.command("list")
@guarded
def watcher_list(key: KeyArg, as_json: JsonOpt = False, out: OutputOpt = None) -> None:
    """Show who watches an issue."""
    session = connect()
    view = session.send(ListWatchers(key))
    output.emit(
        view.to_json(),
        [
            Column("Name", lambda u: u["name"], style="bold"),
            Column("Account id", lambda u: u["accountId"], style="dim"),
            Column("Active", lambda u: "yes" if u["active"] else "no"),
        ],
        fmt(as_json, chosen=out),
        empty=f"Nobody watches {view.key}.",
    )


@watcher_app.command("add")
@guarded
def watcher_add(
    key: KeyArg,
    who: Annotated[str, typer.Argument(help="Email, account id, name or @me.")] = "@me",
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Start watching an issue (you, by default, or someone else).

    For many issues at once, see [bold]acli-py issue watch[/].
    """
    _watch(key, who, True, yes, dry_run)


@watcher_app.command("remove")
@guarded
def watcher_remove(
    key: KeyArg,
    who: Annotated[str, typer.Argument(help="Email, account id, name or @me.")] = "@me",
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Stop someone (you, by default) watching an issue.

    For many issues at once, see [bold]acli-py issue unwatch[/].
    """
    _watch(key, who, False, yes, dry_run)


def _watch(key: str, who: str, watch: bool, yes: bool, dry_run: bool) -> None:
    session = connect(dry_run)
    account = session.account_id(who)
    name = "" if account == session.me else who
    done = "now watched" if watch else "no longer watched"
    run_many(
        session,
        [WatchIssue(key, account, watch, name)],
        done=("would be " if session.dry_run else "")
        + done
        + (f" by {escape(name)}" if name else ""),
        yes=yes,
    )


# ── worklogs ─────────────────────────────────────────────────────────────────

worklog_app = typer.Typer(help="Log time and see logged work.", no_args_is_help=True)


@worklog_app.command("list")
@guarded
def worklog_list(key: KeyArg, as_json: JsonOpt = False, out: OutputOpt = None) -> None:
    """Show the work logged on an issue."""
    session = connect()
    view = session.send(ListWorklogs(key))
    output.emit(
        view.to_json(),
        [
            Column("Id", lambda w: w["id"], style="dim"),
            Column("Who", lambda w: dig(w, "author", "name"), style="bold"),
            Column("Started", lambda w: when(w["started"])),
            Column("Time", lambda w: w["timeSpent"], justify="right"),
            Column("Comment", lambda w: w["comment"]),
        ],
        fmt(as_json, chosen=out),
        empty=f"No work logged on {view.key}.",
    )


@worklog_app.command("add")
@guarded
def worklog_add(
    keys: Annotated[
        list[str] | None,
        typer.Argument(
            help="Issue keys ('-' reads them from stdin), then the time unless --time gives it: "
            "DEMO-1 1h 30m.",
            show_default=False,
        ),
    ] = None,
    time: Annotated[
        str | None,
        typer.Option("--time", "-t", help="Time spent, Jira style: 1h 30m, 2d, 45m."),
    ] = None,
    comment: Annotated[str | None, typer.Option("--comment", "-m", help="What you did.")] = None,
    started: Annotated[
        str | None,
        typer.Option("--started", help="When: YYYY-MM-DD or YYYY-MM-DDTHH:MM (default: now)."),
    ] = None,
    estimate: Annotated[
        str | None,
        typer.Option("--remaining", help="Set the remaining estimate, e.g. 3h (default: auto)."),
    ] = None,
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
    """Log time on one or many issues.

    [dim]acli-py issue worklog add DEMO-1 1h 30m -m Pairing
    acli-py issue worklog add --jql 'sprint in openSprints() and assignee = currentUser()' -t 15m[/]
    """
    keys = list(keys or [])
    if time is None and len(keys) > 1 and not looks_like_key(keys[-1]):
        keys, time = keys[:1], " ".join(keys[1:])
    if not time:
        raise fail("How long? Give the time after the key, or as [bold]--time 1h 30m[/].")
    if not is_duration(time):
        raise fail(f"{escape(time)!r} is not a duration like 1h 30m, 2d or 45m.")
    moment = _moment(started) if started else None
    session = connect(dry_run)
    picked = pick_issues(
        session, keys or None, jql, saved_filter, from_file, limit=limit, force=force
    )
    run_many(
        session,
        [LogWork(k, time, comment or "", moment, estimate or "") for k in picked],
        done=f"would get {time}" if session.dry_run else f"logged {time}",
        yes=yes,
        concurrency=concurrency,
        keep_going=keep_going,
        force=force,
        as_json=as_json,
        describe=lambda r: "" if session.dry_run else f"[dim](id {r.after.get('worklog')})[/]",
    )


@worklog_app.command("delete")
@guarded
def worklog_delete(
    key: KeyArg,
    worklog_ids: Annotated[list[str], typer.Argument(help="Worklog ids.")],
    keep_going: KeepGoingOpt = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Delete logged work."""
    session = connect(dry_run)
    run_many(
        session,
        [DeleteWorklog(key, wid) for wid in _ids(worklog_ids)],
        done="would be deleted" if session.dry_run else "deleted",
        yes=yes,
        keep_going=keep_going,
        concurrency=1,
    )


def _moment(text: str) -> datetime:
    """Return a date (at 09:00) or a local date-time the user typed."""
    text = text.strip()
    try:
        return datetime.fromisoformat(text if "T" in text or " " in text else f"{text}T09:00")
    except ValueError:
        raise fail(f"{escape(text)!r} is not a date like 2026-09-24 or 2026-09-24T14:30.") from None
