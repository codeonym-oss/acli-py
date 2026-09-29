"""The parts of an issue: comments, links, attachments, watchers and worklogs."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.markdown import Markdown
from rich.markup import escape

from acli_py import adf, output, resolve
from acli_py.cli.common import (
    AllOpt,
    DryRunOpt,
    FilterOpt,
    FromFileOpt,
    IgnoreErrorsOpt,
    JqlOpt,
    JsonOpt,
    KeysArg,
    LimitOpt,
    YesOpt,
    confirm,
    connect,
    edit_text,
    fail,
    fmt,
    guarded,
    limit_of,
    run_bulk,
)
from acli_py.client import API
from acli_py.fields import when
from acli_py.output import Column, dig

KeyArg = Annotated[str, typer.Argument(help="Issue key, e.g. DEMO-12.")]


def _visibility(role: str | None, group: str | None) -> dict | None:
    if role and group:
        raise fail("Restrict a comment to a role or a group, not both.")
    if role:
        return {"type": "role", "value": role}
    if group:
        return {"type": "group", "value": group}
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


def _body(session: Any, body: str | None, body_file: Path | None, editor: bool) -> dict:
    text = resolve.read_text_arg(body, body_file)
    if editor:
        text = edit_text(text or "", config=session.config)
    if not text or not text.strip():
        raise fail("The comment is empty: pass [bold]-b TEXT[/], [bold]-B FILE[/] or --editor.")
    return adf.to_adf(text)


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
    comments = list(
        session.client.paged(
            f"{API}/issue/{key.upper()}/comment",
            key="comments",
            limit=limit_of(limit, all_pages),
            orderBy="-created" if newest_first else "created",
        )
    )
    if as_json:
        output.print_json(comments)
        return
    if not comments:
        output.info(f"{key.upper()} has no comments.")
    for c in comments:
        seen_by = dig(c, "visibility", "value")
        output.console.print(
            f"[bold]{escape(dig(c, 'author', 'displayName', default='?'))}[/] "
            f"[dim]{when(c.get('created'))} · id {c.get('id')}"
            + (
                f" · edited {when(c.get('updated'))}"
                if c.get("updated") != c.get("created")
                else ""
            )
            + (f" · visible to {escape(seen_by)}" if seen_by else "")
            + "[/]"
        )
        output.console.print(Markdown(adf.to_text(c.get("body")) or "_(empty)_"))
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
    yes: YesOpt = False,
    ignore_errors: IgnoreErrorsOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Comment on one or many issues.

    [dim]aj issue comment add DEMO-3 -b "Fixed in **2.4**"
    echo "Deployed" | aj issue comment add --jql 'fixVersion = 2.4' -b - -y[/]
    """
    session = connect(dry_run)
    picked = resolve.targets(session.client, keys, jql, saved_filter, from_file)
    payload: dict[str, Any] = {"body": _body(session, body, body_file, editor)}
    if visibility := _visibility(role, group):
        payload["visibility"] = visibility
    if len(picked) > 1:
        confirm(f"Comment on {len(picked)} issues?", yes, session)

    def one(key: str) -> dict:
        if edit_last:
            mine = [
                c
                for c in session.client.paged(
                    f"{API}/issue/{key}/comment", key="comments", orderBy="-created"
                )
                if dig(c, "author", "accountId") == session.me
            ]
            if mine:
                return session.client.put(f"{API}/issue/{key}/comment/{mine[0]['id']}", payload)
        return session.client.post(f"{API}/issue/{key}/comment", payload)

    run_bulk(
        picked,
        one,
        done="would get the comment" if session.dry_run else "commented",
        ignore_errors=ignore_errors,
        as_json=as_json,
        describe=lambda _k, r: "" if r.get("dryRun") else f"[dim](id {r.get('id')})[/]",
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
    dry_run: DryRunOpt = False,
) -> None:
    """Replace a comment's text."""
    session = connect(dry_run)
    path = f"{API}/issue/{key.upper()}/comment/{comment_id}"
    if editor and body is None and body_file is None:
        body = adf.to_text(session.client.get(path).get("body"))
    payload: dict[str, Any] = {"body": _body(session, body, body_file, editor)}
    if visibility := _visibility(role, group):
        payload["visibility"] = visibility
    session.client.put(path, payload, notifyUsers="true" if notify else "false")
    if not session.dry_run:
        output.success(f"Comment {comment_id} on {key.upper()} updated")


@comment_app.command("delete")
@guarded
def comment_delete(
    key: KeyArg,
    comment_ids: Annotated[list[str], typer.Argument(help="Comment ids.")],
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Delete comments."""
    session = connect(dry_run)
    confirm(f"Delete {len(comment_ids)} comment(s) from {key.upper()}?", yes, session)
    run_bulk(
        comment_ids,
        lambda cid: session.client.delete(f"{API}/issue/{key.upper()}/comment/{cid}"),
        done="would be deleted" if session.dry_run else "deleted",
    )


@comment_app.command("visibility")
@guarded
def comment_visibility(
    project: Annotated[
        str | None, typer.Option("--project", "-p", help="Show this project's roles.")
    ] = None,
    as_json: JsonOpt = False,
) -> None:
    """List the roles (with --project) or groups a comment can be restricted to."""
    session = connect()
    if project:
        roles = session.client.get(f"{API}/project/{project.upper()}/role")
        rows = [{"type": "role", "name": name} for name in sorted(roles)]
    else:
        found = session.client.get(f"{API}/groups/picker", maxResults=100)
        rows = [{"type": "group", "name": g["name"]} for g in found.get("groups", [])]
    columns = [
        Column("Type", lambda r: r["type"], style="dim"),
        Column("Name", lambda r: r["name"]),
    ]
    output.emit(rows, columns, fmt(as_json))


# ── links ────────────────────────────────────────────────────────────────────

link_app = typer.Typer(help="Link issues to each other.", no_args_is_help=True)


def link_body(client: Any, source: str, kind: str, target: str) -> tuple[dict, str]:
    """Return the issueLink payload for "SOURCE <kind> TARGET", and the sentence it says."""
    link_type, outward = resolve.link_type(client, kind)
    if not outward:
        source, target = target, source
    # POST /issueLink: the outward ("from") issue is the one the outward phrase starts with.
    body = {
        "type": {"name": link_type["name"]},
        "outwardIssue": {"key": source.upper()},
        "inwardIssue": {"key": target.upper()},
    }
    return body, f"{source.upper()} {link_type['outward']} {target.upper()}"


@link_app.command("add")
@guarded
def link_add(
    source: Annotated[
        str | None, typer.Argument(help="The issue the sentence starts with.")
    ] = None,
    kind: Annotated[
        str | None,
        typer.Argument(help="Link type or phrase: blocks, 'is blocked by', relates to, Duplicate…"),
    ] = None,
    target: Annotated[str | None, typer.Argument(help="The other issue.")] = None,
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
    yes: YesOpt = False,
    ignore_errors: IgnoreErrorsOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Link two issues, read as a sentence.

    [dim]aj issue link add DEMO-1 blocks DEMO-2
    aj issue link add DEMO-5 "is duplicated by" DEMO-9[/]
    """
    if template:
        output.print_json(
            [
                {"from": "DEMO-1", "type": "blocks", "to": "DEMO-2"},
                {"from": "DEMO-3", "type": "is duplicated by", "to": "DEMO-4"},
            ]
        )
        return
    session = connect(dry_run)
    triples: list[tuple[str, str, str]] = []
    if from_json:
        triples += [
            (str(r["from"]), str(r["type"]), str(r["to"]))
            for r in json.loads(from_json.read_text(encoding="utf-8"))
        ]
    if from_csv:
        rows = list(csv.reader(from_csv.read_text(encoding="utf-8-sig").splitlines()))
        triples += [(r[0], r[1], r[2]) for r in rows[1:] if len(r) >= 3]
    if source or kind or target:
        if not (source and kind and target):
            raise fail("Give three words: [bold]aj issue link add FROM TYPE TO[/].")
        triples.append((source, kind, target))
    if not triples:
        raise fail("Nothing to link. See [bold]aj issue link add --help[/].")
    if len(triples) > 1:
        confirm(f"Create {len(triples)} links?", yes, session)
    labels = {f"{a.upper()} {k} {b.upper()}": (a, k, b) for a, k, b in triples}

    def one(label: str) -> None:
        body, _ = link_body(session.client, *labels[label])
        if comment:
            body["comment"] = {"body": adf.to_adf(comment)}
        session.client.post(f"{API}/issueLink", body)

    run_bulk(
        list(labels),
        one,
        done="would be linked" if session.dry_run else "linked",
        ignore_errors=ignore_errors,
    )


@link_app.command("list")
@guarded
def link_list(key: KeyArg, as_json: JsonOpt = False) -> None:
    """Show an issue's links."""
    session = connect()
    links = session.client.issue(key.upper(), ["issuelinks"])["fields"].get("issuelinks", [])

    def phrase(link: dict) -> str:
        kind = link.get("type", {})
        return kind.get("outward") if "outwardIssue" in link else kind.get("inward")

    def other(link: dict) -> dict:
        return link.get("outwardIssue") or link.get("inwardIssue") or {}

    output.emit(
        links,
        [
            Column("Link id", lambda r: r.get("id"), style="dim"),
            Column("Relation", phrase),
            Column("Issue", lambda r: other(r).get("key"), style="cyan"),
            Column("Status", lambda r: dig(other(r), "fields", "status", "name")),
            Column("Summary", lambda r: dig(other(r), "fields", "summary")),
        ],
        fmt(as_json),
        empty=f"{key.upper()} has no links.",
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
    yes: YesOpt = False,
    ignore_errors: IgnoreErrorsOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Remove links between issues."""
    ids = [i for value in link_ids or [] for i in re.split(r"[\s,]+", value) if i]
    if from_json:
        ids += [
            str(v["id"] if isinstance(v, dict) else v) for v in json.loads(from_json.read_text())
        ]
    if from_csv:
        rows = list(csv.reader(from_csv.read_text(encoding="utf-8-sig").splitlines()))
        ids += [r[0] for r in rows if r and r[0].strip().isdigit()]
    if not ids:
        raise fail("Which links? Give ids; [bold]aj issue link list KEY[/] shows them.")
    session = connect(dry_run)
    confirm(f"Delete {len(ids)} link(s)?", yes, session)
    run_bulk(
        ids,
        lambda lid: session.client.delete(f"{API}/issueLink/{lid}"),
        done="would be deleted" if session.dry_run else "deleted",
        ignore_errors=ignore_errors,
    )


@link_app.command("types")
@guarded
def link_types(as_json: JsonOpt = False) -> None:
    """List the kinds of link the site offers."""
    session = connect()
    output.emit(
        session.client.link_types(),
        [
            Column("Id", lambda t: t.get("id"), style="dim"),
            Column("Name", lambda t: t.get("name"), style="bold"),
            Column("Outward (A … B)", lambda t: t.get("outward")),
            Column("Inward (B … A)", lambda t: t.get("inward")),
        ],
        fmt(as_json),
    )


# ── attachments ──────────────────────────────────────────────────────────────

attachment_app = typer.Typer(
    help="List, upload, download and delete attachments.", no_args_is_help=True
)


@attachment_app.command("list")
@guarded
def attachment_list(key: KeyArg, as_json: JsonOpt = False) -> None:
    """Show an issue's attachments."""
    session = connect()
    files = session.client.issue(key.upper(), ["attachment"])["fields"].get("attachment", [])
    output.emit(
        files,
        [
            Column("Id", lambda a: a.get("id"), style="dim"),
            Column("File", lambda a: a.get("filename"), style="bold"),
            Column("Size", lambda a: f"{a.get('size', 0):,} B", justify="right"),
            Column("Type", lambda a: a.get("mimeType"), style="dim"),
            Column("By", lambda a: dig(a, "author", "displayName")),
            Column("Added", lambda a: when(a.get("created"))),
        ],
        fmt(as_json),
        empty=f"{key.upper()} has no attachments.",
    )


@attachment_app.command("upload")
@guarded
def attachment_upload(
    key: KeyArg,
    files: Annotated[
        list[Path], typer.Argument(help="Files to attach.", exists=True, dir_okay=False)
    ],
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Attach files to an issue."""
    session = connect(dry_run)
    uploaded: list[dict] = []
    for path in files:
        with path.open("rb") as handle:
            result = session.client.request(
                "POST",
                f"{API}/issue/{key.upper()}/attachments",
                files={"file": (path.name, handle)},
                headers={"X-Atlassian-Token": "no-check"},
            )
        if isinstance(result, list):
            uploaded.extend(result)
        if not session.dry_run:
            output.success(f"Attached {escape(path.name)} to {key.upper()}")
    if as_json:
        output.print_json(uploaded)


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
    for attachment_id in attachment_ids:
        meta = session.client.get(f"{API}/attachment/{attachment_id}")
        dest = out / Path(meta.get("filename", attachment_id)).name
        size = session.client.download(f"{API}/attachment/content/{attachment_id}", dest)
        output.success(f"Saved {escape(str(dest))} ({size:,} bytes)")


@attachment_app.command("delete")
@guarded
def attachment_delete(
    attachment_ids: Annotated[list[str], typer.Argument(help="Attachment ids.")],
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Delete attachments by id."""
    session = connect(dry_run)
    confirm(f"Delete {len(attachment_ids)} attachment(s)?", yes, session)
    run_bulk(
        attachment_ids,
        lambda aid: session.client.delete(f"{API}/attachment/{aid}"),
        done="would be deleted" if session.dry_run else "deleted",
    )


# ── watchers ─────────────────────────────────────────────────────────────────

watcher_app = typer.Typer(help="See, add and remove watchers.", no_args_is_help=True)
UserArg = Annotated[str, typer.Argument(help="Email, account id, name or @me.")]


@watcher_app.command("list")
@guarded
def watcher_list(key: KeyArg, as_json: JsonOpt = False) -> None:
    """Show who watches an issue."""
    session = connect()
    data = session.client.get(f"{API}/issue/{key.upper()}/watchers")
    output.emit(
        data.get("watchers", []),
        [
            Column("Name", lambda u: u.get("displayName"), style="bold"),
            Column("Account id", lambda u: u.get("accountId"), style="dim"),
            Column("Active", lambda u: "yes" if u.get("active", True) else "no"),
        ],
        fmt(as_json),
        empty=f"Nobody watches {key.upper()}.",
    )


@watcher_app.command("add")
@guarded
def watcher_add(
    key: KeyArg,
    who: Annotated[str, typer.Argument(help="Email, account id, name or @me.")] = "@me",
    dry_run: DryRunOpt = False,
) -> None:
    """Start watching an issue (you, by default, or someone else)."""
    session = connect(dry_run)
    account = resolve.user(session.client, who, session.me)["accountId"]
    session.client.post(f"{API}/issue/{key.upper()}/watchers", account)
    if not session.dry_run:
        output.success(f"{escape(who)} now watches {key.upper()}")


@watcher_app.command("remove")
@guarded
def watcher_remove(
    key: KeyArg,
    who: Annotated[str, typer.Argument(help="Email, account id, name or @me.")] = "@me",
    dry_run: DryRunOpt = False,
) -> None:
    """Stop someone (you, by default) watching an issue."""
    session = connect(dry_run)
    account = resolve.user(session.client, who, session.me)["accountId"]
    session.client.delete(f"{API}/issue/{key.upper()}/watchers", accountId=account)
    if not session.dry_run:
        output.success(f"{escape(who)} no longer watches {key.upper()}")


# ── worklogs ─────────────────────────────────────────────────────────────────

worklog_app = typer.Typer(help="Log time and see logged work.", no_args_is_help=True)

DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?\s*[wdhm]\s*)+$", re.IGNORECASE)


@worklog_app.command("list")
@guarded
def worklog_list(key: KeyArg, as_json: JsonOpt = False) -> None:
    """Show the work logged on an issue."""
    session = connect()
    logs = list(session.client.paged(f"{API}/issue/{key.upper()}/worklog", key="worklogs"))
    output.emit(
        logs,
        [
            Column("Id", lambda w: w.get("id"), style="dim"),
            Column("Who", lambda w: dig(w, "author", "displayName"), style="bold"),
            Column("Started", lambda w: when(w.get("started"))),
            Column("Time", lambda w: w.get("timeSpent"), justify="right"),
            Column("Comment", lambda w: " ".join(adf.to_text(w.get("comment")).split())),
        ],
        fmt(as_json),
        empty=f"No work logged on {key.upper()}.",
    )


@worklog_app.command("add")
@guarded
def worklog_add(
    key: KeyArg,
    time: Annotated[str, typer.Argument(help="Time spent, Jira style: 1h 30m, 2d, 45m.")],
    comment: Annotated[str | None, typer.Option("--comment", "-m", help="What you did.")] = None,
    started: Annotated[
        str | None,
        typer.Option("--started", help="When: YYYY-MM-DD or YYYY-MM-DDTHH:MM (default: now)."),
    ] = None,
    estimate: Annotated[
        str | None,
        typer.Option("--remaining", help="Set the remaining estimate, e.g. 3h (default: auto)."),
    ] = None,
    dry_run: DryRunOpt = False,
) -> None:
    """Log time on an issue."""
    if not DURATION.match(time):
        raise fail(f"{escape(time)!r} is not a duration like 1h 30m, 2d or 45m.")
    session = connect(dry_run)
    body: dict[str, Any] = {"timeSpent": time.strip()}
    if comment:
        body["comment"] = adf.to_adf(comment)
    if started:
        body["started"] = _jira_datetime(started)
    params = {"adjustEstimate": "new", "newEstimate": estimate} if estimate else {}
    result = session.client.post(f"{API}/issue/{key.upper()}/worklog", body, **params)
    if not session.dry_run:
        output.success(f"Logged {escape(time)} on {key.upper()} [dim](id {result.get('id')})[/]")


@worklog_app.command("delete")
@guarded
def worklog_delete(
    key: KeyArg,
    worklog_ids: Annotated[list[str], typer.Argument(help="Worklog ids.")],
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Delete logged work."""
    session = connect(dry_run)
    confirm(f"Delete {len(worklog_ids)} worklog(s) from {key.upper()}?", yes, session)
    run_bulk(
        worklog_ids,
        lambda wid: session.client.delete(f"{API}/issue/{key.upper()}/worklog/{wid}"),
        done="would be deleted" if session.dry_run else "deleted",
    )


def _jira_datetime(text: str) -> str:
    """Return Jira's worklog timestamp form for a date or local date-time."""
    from datetime import datetime

    text = text.strip()
    moment = datetime.fromisoformat(text if "T" in text or " " in text else f"{text}T09:00")
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000%z")
