"""What every command shares: options, the session, confirmations and bulk runs."""

from __future__ import annotations

import asyncio
import dataclasses
import functools
import os
import shlex
import subprocess
import tempfile
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import unquote

import requests
import typer
from rich.markup import escape
from rich.table import Table

from acli_py.application.bulk import CONCURRENCY, MAX_CONCURRENCY, SAFETY_CAP, Report, TooManyError
from acli_py.application.bus import Bus
from acli_py.application.changes import Change, Declined
from acli_py.application.site import Site
from acli_py.bootstrap import build_bus, build_catalog
from acli_py.domain.jql import compile_query, looks_like_jql
from acli_py.domain.jql.catalog import spelling
from acli_py.infrastructure import credentials
from acli_py.infrastructure.config import Account, Config
from acli_py.infrastructure.jira import resolve
from acli_py.infrastructure.jira.client import JiraClient, JiraError, normalize_url, site_host
from acli_py.infrastructure.jira.resolve import ResolveError
from acli_py.presentation import output, terminal
from acli_py.presentation.output import Format, pick_format

TRUTHY = ("1", "true", "yes", "on")

# Commands over many issues exit 1 when some failed, and this when nothing ran: the change
# was declined, or went over the safety cap.
EXIT_ABORTED = 2
# The reader of our output went away (`| head`): stop quietly, as a shell tool killed by
# SIGPIPE would (128 + 13).
EXIT_BROKEN_PIPE = 141


# ── process-wide state set by the root callback ──────────────────────────────


@dataclass
class State:
    """Options given before the command (`acli-py --dry-run --debug issue …`)."""

    dry_run: bool = False
    debug: bool = False
    account: str | None = None
    clients: list[JiraClient] = field(default_factory=list)


state = State()


def env_flag(name: str) -> bool:
    """Return whether an environment variable is set to a truthy value."""
    return os.environ.get(name, "").strip().lower() in TRUTHY


# ── shared options ───────────────────────────────────────────────────────────

DryRunOpt = Annotated[
    bool,
    typer.Option(
        "--dry-run",
        "-n",
        help="Show what would change without changing anything. Reads still run.",
    ),
]
YesOpt = Annotated[bool, typer.Option("--yes", "-y", help="Don't ask for confirmation.")]
JsonOpt = Annotated[bool, typer.Option("--json", help="Print JSON.")]
CsvOpt = Annotated[bool, typer.Option("--csv", help="Print CSV.")]
OutputOpt = Annotated[
    Format | None,
    typer.Option(
        "--output",
        help="How to print: table, json, csv, or keys / jsonl (one per line, for pipes).",
        show_default=False,
    ),
]
LimitOpt = Annotated[
    int, typer.Option("--limit", "-l", min=1, help="Show at most this many results.")
]
AllOpt = Annotated[bool, typer.Option("--all", "-A", help="Fetch every page, ignoring --limit.")]
WebOpt = Annotated[bool, typer.Option("--web", "-w", help="Open it in the browser instead.")]
IgnoreErrorsOpt = Annotated[
    bool,
    typer.Option("--ignore-errors", help="Keep going when one item fails; exit 1 at the end."),
]

# Picking issues for bulk commands.
KeysArg = Annotated[
    list[str] | None,
    typer.Argument(
        help="Issue keys (DEMO-1 DEMO-2, or DEMO-1,DEMO-2); '-' reads keys or JSON lines "
        "from stdin.",
        show_default=False,
    ),
]
JqlOpt = Annotated[
    str | None,
    typer.Option("--jql", "-q", help="Act on the issues this JQL or smart query finds."),
]
FilterOpt = Annotated[
    str | None, typer.Option("--filter", help="Act on the issues of this saved filter id.")
]
FromFileOpt = Annotated[
    Path | None,
    typer.Option(
        "--from-file",
        "-f",
        help="Read issue keys from a file (commas, spaces or lines; '-' for stdin).",
    ),
]
# Running a command over many issues (the bulk engine).
ConcurrencyOpt = Annotated[
    int,
    typer.Option(
        "--concurrency",
        "-c",
        min=1,
        max=MAX_CONCURRENCY,
        help="How many issues to work on at once.",
    ),
]
KeepGoingOpt = Annotated[
    bool,
    typer.Option(
        "--continue-on-error",
        "--ignore-errors",
        help="Keep going when an issue fails (else stop starting new ones); exit 1 at the end.",
    ),
]
BulkLimitOpt = Annotated[
    int | None,
    typer.Option(
        "--limit", "-l", min=1, help="Act on at most this many issues.", show_default=False
    ),
]
ForceOpt = Annotated[
    bool,
    typer.Option("--force", help=f"Allow acting on more than {SAFETY_CAP} issues at once."),
]
ProjectOpt = Annotated[
    str | None,
    typer.Option("--project", "-p", help="Project key (default: `acli-py config set project`)."),
]


def limit_of(limit: int, all_pages: bool) -> int | None:
    """Return the item limit, or None to fetch everything."""
    return None if all_pages else limit


def fmt(as_json: bool = False, as_csv: bool = False, chosen: Format | None = None) -> Format:
    """Return the chosen output format (--json, --csv or --output)."""
    return pick_format(as_json, as_csv, chosen)


# ── errors ───────────────────────────────────────────────────────────────────


def fail(message: str, code: int = 1) -> typer.Exit:
    """Print an error line and return the exit to raise."""
    output.error(message)
    return typer.Exit(code)


def guarded(command: Callable) -> Callable:
    """Turn the errors a user can act on into one red line instead of a traceback."""

    @functools.wraps(command)
    def wrapper(*args: object, **kwargs: object) -> object:
        try:
            return command(*args, **kwargs)
        except TooManyError as error:
            raise fail(
                f"{error} Narrow it down, or pass [bold]--force[/] to go ahead.", EXIT_ABORTED
            ) from None
        except (JiraError, ResolveError, credentials.CredentialError, ValueError) as error:
            raise fail(escape(str(error))) from None
        except Declined as declined:
            raise fail(escape(str(declined)), EXIT_ABORTED) from None
        except BrokenPipeError:
            output.silence_stdout()
            raise typer.Exit(EXIT_BROKEN_PIPE) from None
        except OSError as error:
            raise fail(escape(f"{error.strerror or error}: {error.filename or ''}")) from None

    return wrapper


# ── the session ──────────────────────────────────────────────────────────────


@dataclass
class Session:
    """An open client for one account, plus the loaded config."""

    client: JiraClient
    account: Account
    config: Config
    _bus: Bus | None = field(default=None, repr=False)

    @property
    def dry_run(self) -> bool:
        """Return whether writes are only shown."""
        return self.client.dry_run

    @property
    def url(self) -> str:
        """Return the site URL."""
        return self.account.url

    @property
    def me(self) -> str:
        """Return the account id of the logged-in user (asking Jira once if unknown)."""
        if not self.account.account_id:
            self.account.account_id = self.client.myself().get("accountId", "")
        return self.account.account_id

    def browse(self, key: str) -> str:
        """Return an issue's web URL."""
        return f"{self.url}/browse/{key}"

    def site(self) -> Site:
        """Return the site the application layer works on."""
        return Site(self.client, self.url, self.account.account_id, self.account.display_name)

    @property
    def bus(self) -> Bus:
        """Return the bus, built on first use; it asks at the terminal before changes."""
        if self._bus is None:
            self._bus = build_bus(self.site(), confirmer=TerminalConfirmer())
        return self._bus

    def bus_to(self, other: Session) -> Bus:
        """Return a bus for this site whose copies (clones) go to `other`'s site."""
        if other.url == self.url:
            return self.bus
        return build_bus(self.site(), confirmer=TerminalConfirmer(), destination=other.site())

    def send(self, message: Any) -> Any:
        """Send a query or command on the bus, and wait for its answer."""
        return asyncio.run(self.bus.send(message))

    def project(self, key: str | None) -> str:
        """Return the given project key, or the configured default, or fail."""
        chosen = key or self.config.defaults.get("project")
        if not chosen:
            raise fail(
                "No project given. Pass [bold]-p KEY[/] or set a default with "
                "[bold]acli-py config set project KEY[/]."
            )
        return chosen.upper()


def trace_response(resp: requests.Response) -> None:
    """Print one line per HTTP response (--debug)."""
    ms = resp.elapsed.total_seconds() * 1000
    url = unquote(resp.request.url or "")
    output.trace.print(
        f"  HTTP {resp.request.method} {resp.status_code} {ms:6.0f} ms  {escape(url)}",
        soft_wrap=True,
    )


def env_account() -> Account | None:
    """Return an account built from ACLI_PY_SITE/EMAIL/API_TOKEN (for CI), if all are set."""
    site, email = os.environ.get("ACLI_PY_SITE"), os.environ.get("ACLI_PY_EMAIL")
    if site and email and os.environ.get("ACLI_PY_API_TOKEN"):
        return Account(url=normalize_url(site), email=email, token_backend="env")
    return None


def find_account(config: Config, wanted: str, option: str = "--account") -> Account:
    """Return the one saved account `wanted` names: email@site, an email, or a site."""
    low = wanted.strip().lower()
    host = site_host(low) if "." in low or ":" in low else low
    matches = [
        a
        for a in config.accounts.values()
        if low in (a.name.lower(), a.email.lower(), a.host.lower()) or host == a.host.lower()
    ]
    if len(matches) != 1:
        raise fail(
            f"{option} {escape(wanted)} matches {len(matches)} saved accounts. "
            "See [bold]acli-py auth status[/]."
        )
    return matches[0]


def pick_account(config: Config) -> Account:
    """Return the account to use: --account, the environment, or the active one."""
    if state.account:
        return find_account(config, state.account)
    if account := env_account():
        return account
    if config.account is None:
        raise fail("Not logged in. Run [bold]acli-py auth login[/] first.")
    return config.account


def connect(dry_run: bool = False, account_name: str | None = None) -> Session:
    """Open a client for the active account (or the one named), closed when the command ends."""
    config = Config.load()
    account = (
        find_account(config, account_name, "--to-site") if account_name else pick_account(config)
    )
    token = credentials.load_token(account.name, account.token_backend)
    if not token:
        raise fail(
            f"No API token saved for {escape(account.name)}. Run [bold]acli-py auth login[/] again."
        )
    client = JiraClient(
        account.url,
        account.email,
        token,
        dry_run=dry_run or state.dry_run or env_flag("ACLI_PY_DRY_RUN"),
        on_response=trace_response if state.debug else None,
        on_plan=output.show_plan,
    )
    state.clients.append(client)
    return Session(client, account, config)


def close_clients() -> None:
    """Close every client the command opened, and sum up a dry run."""
    while state.clients:
        client = state.clients.pop()
        if client.dry_run:
            count = len(client.planned)
            output.errors.print(
                f"[bold magenta]DRY RUN[/] {count} change{'s' if count != 1 else ''} "
                "planned, nothing was sent to Jira."
            )
        client.close()


# ── interaction ──────────────────────────────────────────────────────────────


def interactive() -> bool:
    """Return whether there is a terminal to ask questions on (mid-pipe, the one behind it)."""
    return terminal.available()


class TerminalConfirmer:
    """The CLI's and the shell's way to ask before a change: a y/N question on stderr.

    A change over several issues shows its preview first: each issue, its value now and after.
    A destructive one over several issues asks the user to type how many, not just y.
    """

    async def confirm(self, change: Change) -> bool:
        """Ask; with no terminal to ask on, refuse and point at --yes."""
        question = f"{change}?"
        if not interactive():
            raise Declined(f"{question} Refusing without --yes (no terminal to ask on).")
        if len(change.preview) > 1:
            output.errors.print(preview_table(change))
        if change.destructive and len(change.keys) > 1:
            count = str(len(change.keys))
            return (
                terminal.answer(f"{question} This can't be undone. Type {count} to agree") == count
            )
        return terminal.ask(question)


def preview_table(change: Change) -> Table:
    """Return a change's preview as a table: issue, summary, now → after."""
    table = Table(box=None, pad_edge=False, header_style="bold dim")
    table.add_column("Issue", style="bold cyan", no_wrap=True)
    table.add_column("Summary", overflow="ellipsis", no_wrap=True, max_width=50)
    table.add_column("Now")
    table.add_column("")
    table.add_column("After", style="bold")
    for row in change.preview:
        arrow = "[dim]=[/]" if row.now.lower() == row.after.lower() else "[dim]→[/]"
        table.add_row(row.key, escape(row.summary), escape(row.now), arrow, escape(row.after))
    return table


def confirm(question: str, yes: bool, session: Session | None = None) -> None:
    """Ask before a change; --yes and dry runs skip the question. Exits when declined."""
    if yes or (session is not None and session.dry_run):
        return
    if not interactive():
        raise fail(f"{question} Refusing without [bold]--yes[/] (no terminal to ask on).")
    if not terminal.ask(question):
        raise fail("Cancelled.", code=1)


def edit_text(initial: str = "", suffix: str = ".md", config: Config | None = None) -> str:
    """Open the user's editor on `initial` and return what they saved."""
    editor = (
        (config.defaults.get("editor") if config else None)
        or os.environ.get("VISUAL")
        or os.environ.get("EDITOR")
        or ("notepad" if os.name == "nt" else "vi")
    )
    fd, name = tempfile.mkstemp(suffix=suffix, prefix="acli-py-")
    path = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(initial)
        subprocess.run([*shlex.split(editor, posix=os.name != "nt"), str(path)], check=True)
        return path.read_text(encoding="utf-8")
    finally:
        path.unlink(missing_ok=True)


def open_url(url: str) -> None:
    """Open `url` in the browser and say so."""
    output.info(f"Opening {escape(url)}")
    webbrowser.open(url)


# ── bulk runs ────────────────────────────────────────────────────────────────


@dataclass
class Outcome:
    """What happened to one item in a bulk run."""

    item: str
    ok: bool
    detail: str = ""
    data: Any = None


def run_bulk(
    items: list[str],
    action: Callable[[str], Any],
    *,
    done: str,
    ignore_errors: bool = False,
    as_json: bool = False,
    describe: Callable[[str, Any], str] | None = None,
) -> list[Outcome]:
    """Apply `action` to each item, printing ✔/✘ per item; exit 1 if anything failed.

    Stops at the first failure unless `ignore_errors`.
    """
    outcomes: list[Outcome] = []
    for item in items:
        try:
            result = action(item)
        except (JiraError, ResolveError, ValueError) as error:
            outcomes.append(Outcome(item, False, str(error)))
            output.error(f"{escape(item)}: {escape(str(error))}")
            if not ignore_errors:
                break
            continue
        detail = describe(item, result) if describe else ""
        outcomes.append(Outcome(item, True, detail, result))
        output.success(f"{escape(item)} {done}" + (f" {detail}" if detail else ""))
    if as_json:
        output.print_json(
            [
                {"item": o.item, "ok": o.ok, "error" if not o.ok else "result": o.detail or o.data}
                for o in outcomes
            ]
        )
    failed = sum(not o.ok for o in outcomes)
    skipped = len(items) - len(outcomes)
    if len(items) > 1:
        summary = f"{len(outcomes) - failed} of {len(items)} {done}"
        if failed:
            summary += f", {failed} failed"
        if skipped:
            summary += f", {skipped} not tried"
        output.info(summary + ".")
    if failed:
        raise typer.Exit(1)
    return outcomes


def pick_issues(
    session: Session,
    keys: list[str] | None,
    jql: str | None = None,
    saved_filter: str | None = None,
    from_file: Path | None = None,
    *,
    limit: int | None = None,
    force: bool = False,
) -> list[str]:
    """Return the issues a bulk command acts on: keys, a JQL or smart query, a filter, a file.

    Stops fetching just past the safety cap (the engine then refuses) unless `force`.
    """
    if jql and not looks_like_jql(jql):
        compiled = compile_query(jql, resolve=spelling(build_catalog(session.client)))
        for warning in compiled.warnings:
            output.warn(escape(warning))
        jql = compiled.jql
    fetch = limit or (None if force else SAFETY_CAP + 1)
    picked = resolve.targets(session.client, keys, jql, saved_filter, from_file, limit=fetch)
    return picked[:limit] if limit else picked


def plain(outcome: Any) -> Any:
    """Return an outcome's result as JSON-ready data."""
    result = outcome.result
    if dataclasses.is_dataclass(result) and not isinstance(result, type):
        return dataclasses.asdict(result)
    return result


def run_many(
    session: Session,
    commands: list[Any],
    *,
    done: str,
    yes: bool = False,
    concurrency: int = CONCURRENCY,
    keep_going: bool = False,
    force: bool = False,
    as_json: bool = False,
    describe: Callable[[Any], str] | None = None,
    line: Callable[[Any], str] | None = None,
    bus: Bus | None = None,
) -> Report:
    """Run one command per issue through the bulk engine: preview, ask once, run, sum up.

    Prints a line per issue as it finishes ('DEMO-1 {done} {describe(result)}', or all of
    `line(result)`) and a summary at the end; exits 1 if any failed.
    """

    def show(outcome: Any) -> None:
        if not outcome.ok:
            output.error(f"{escape(outcome.key)}: {escape(outcome.error)}")
            return
        if line is not None:
            output.success(line(outcome.result))
            return
        detail = describe(outcome.result) if describe else ""
        output.success(f"{escape(outcome.key)} {done}" + (f" {detail}" if detail else ""))

    report: Report = asyncio.run(
        (bus or session.bus).bulk.run(
            commands,
            yes=yes,
            concurrency=concurrency,
            keep_going=keep_going,
            force=force,
            on_outcome=None if as_json else show,
        )
    )
    if as_json:
        output.print_json(
            [
                {"item": o.key, "ok": o.ok, "error" if not o.ok else "result": o.error or plain(o)}
                for o in report.outcomes
            ]
        )
    if report.total > 1 and not as_json:
        summary = f"{len(report.succeeded)} of {report.total} {done}"
        if report.failed:
            summary += f", {len(report.failed)} failed"
        if report.not_tried:
            summary += f", {report.not_tried} not tried"
        output.info(summary + ".")
    if report.exit_code:
        raise typer.Exit(report.exit_code)
    return report


def plural(count: int, word: str) -> str:
    """Return '1 issue' / '3 issues'."""
    return f"{count} {word}{'' if count == 1 else 's'}"


def host_of(url: str) -> str:
    """Return a site URL's host (re-exported for commands)."""
    return site_host(url)
