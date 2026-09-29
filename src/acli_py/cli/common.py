"""What every command shares: options, the session, confirmations and bulk runs."""

from __future__ import annotations

import functools
import os
import shlex
import subprocess
import sys
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

from acli_py import credentials, output
from acli_py.client import JiraClient, JiraError, normalize_url, site_host
from acli_py.config import Account, Config
from acli_py.output import Format, pick_format
from acli_py.resolve import ResolveError

TRUTHY = ("1", "true", "yes", "on")


# ── process-wide state set by the root callback ──────────────────────────────


@dataclass
class State:
    """Options given before the command (`aj --dry-run --debug issue …`)."""

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
    typer.Argument(help="Issue keys (DEMO-1 DEMO-2, or DEMO-1,DEMO-2).", show_default=False),
]
JqlOpt = Annotated[
    str | None, typer.Option("--jql", "-q", help="Act on the issues this JQL finds.")
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
ProjectOpt = Annotated[
    str | None,
    typer.Option("--project", "-p", help="Project key (default: `aj config set project`)."),
]


def limit_of(limit: int, all_pages: bool) -> int | None:
    """Return the item limit, or None to fetch everything."""
    return None if all_pages else limit


def fmt(as_json: bool = False, as_csv: bool = False) -> Format:
    """Return the chosen output format."""
    return pick_format(as_json, as_csv)


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
        except (JiraError, ResolveError, credentials.CredentialError, ValueError) as error:
            raise fail(escape(str(error))) from None
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

    def project(self, key: str | None) -> str:
        """Return the given project key, or the configured default, or fail."""
        chosen = key or self.config.defaults.get("project")
        if not chosen:
            raise fail(
                "No project given. Pass [bold]-p KEY[/] or set a default with "
                "[bold]aj config set project KEY[/]."
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
            "See [bold]aj auth status[/]."
        )
    return matches[0]


def pick_account(config: Config) -> Account:
    """Return the account to use: --account, the environment, or the active one."""
    if state.account:
        return find_account(config, state.account)
    if account := env_account():
        return account
    if config.account is None:
        raise fail("Not logged in. Run [bold]aj auth login[/] first.")
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
            f"No API token saved for {escape(account.name)}. Run [bold]aj auth login[/] again."
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


def confirm(question: str, yes: bool, session: Session | None = None) -> None:
    """Ask before a change; --yes and dry runs skip the question. Exits when declined."""
    if yes or (session is not None and session.dry_run):
        return
    if not sys.stdin.isatty():
        raise fail(f"{question} Refusing without [bold]--yes[/] (no terminal to ask on).")
    if not typer.confirm(question, default=False, err=True):
        raise fail("Cancelled.", code=1)


def edit_text(initial: str = "", suffix: str = ".md", config: Config | None = None) -> str:
    """Open the user's editor on `initial` and return what they saved."""
    editor = (
        (config.defaults.get("editor") if config else None)
        or os.environ.get("VISUAL")
        or os.environ.get("EDITOR")
        or ("notepad" if os.name == "nt" else "vi")
    )
    fd, name = tempfile.mkstemp(suffix=suffix, prefix="aj-")
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


def plural(count: int, word: str) -> str:
    """Return '1 issue' / '3 issues'."""
    return f"{count} {word}{'' if count == 1 else 's'}"


def host_of(url: str) -> str:
    """Return a site URL's host (re-exported for commands)."""
    return site_host(url)
