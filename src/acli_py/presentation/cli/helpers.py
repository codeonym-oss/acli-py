"""Everyday helpers: `acli-py standup`, `git branch` / `git commit-msg`, and `alias` (`@name`).

Each is a query with a view, printed as a table or as `--output json|jsonl|markdown|csv`.
"""

from __future__ import annotations

import shlex
from datetime import date
from typing import Annotated, Any

import typer
from rich.markup import escape
from typer.core import TyperGroup

from acli_py.application.queries.issue_columns import split
from acli_py.application.queries.name_for_git.query import NameForGit
from acli_py.application.queries.search_issues.view import IssuesView
from acli_py.application.queries.standup.query import Standup
from acli_py.bootstrap import saved_views
from acli_py.presentation import output
from acli_py.presentation.cli.common import (
    FieldsOpt,
    JsonOpt,
    OutputOpt,
    connect,
    fail,
    fmt,
    guarded,
    show_issues,
)
from acli_py.presentation.output import Column, Format

git_app = typer.Typer(help="Name branches and commits after issues.", no_args_is_help=True)
alias_app = typer.Typer(
    help="Save a query or a command line under a name; run it as `acli-py @name`.",
    no_args_is_help=True,
)

ALIAS = "@"


# ── @aliases ─────────────────────────────────────────────────────────────────


def expand(args: list[str]) -> list[str]:
    """Return a command line with a leading `@name` replaced by what the alias runs.

    A query alias runs `issue search QUERY`; a command alias its own words. Arguments after
    `@name` are added at the end: `acli-py @mine --fields key,due`. Raises `LookupError` for
    a name no alias has.
    """
    if not args or not args[0].startswith(ALIAS) or len(args[0]) == len(ALIAS):
        return args
    name = args[0][len(ALIAS) :]
    alias = saved_views().find_alias(name)
    if alias is None:
        raise LookupError(f"No alias called {name!r}. See `acli-py alias list`.")
    head = shlex.split(alias.query) if alias.command else ["issue", "search", alias.query]
    return [*head, *args[1:]]


class AliasGroup(TyperGroup):
    """The root command group: it reads `@name` as the alias it names."""

    # Typer bundles its own click, so its objects are typed loosely here (as in the shell).
    def resolve_command(self, ctx: Any, args: list[str]) -> Any:
        """Expand an alias, then find the command as usual."""
        try:
            return super().resolve_command(ctx, expand(args))
        except LookupError as error:
            return ctx.fail(str(error))  # raises the usage error the CLI shows


@alias_app.command("list")
@guarded
def alias_list(as_json: JsonOpt = False, out: OutputOpt = None) -> None:
    """List the aliases: the TUI's views (queries) and saved command lines."""
    rows = [
        {
            "name": v.name,
            "kind": "command" if v.command else "query",
            "value": v.query,
            "builtin": v.builtin,
        }
        for v in saved_views().aliases()
    ]
    output.emit(
        rows,
        [
            Column("Name", lambda r: f"{ALIAS}{r['name']}", style="cyan"),
            Column("Kind", lambda r: r["kind"] + (" (built in)" if r["builtin"] else "")),
            Column("Runs", lambda r: r["value"]),
        ],
        fmt(as_json, chosen=out),
    )


@alias_app.command(
    "set", context_settings={"ignore_unknown_options": True, "allow_extra_args": False}
)
@guarded
def alias_set(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The alias: run it as @NAME.")],
    value: Annotated[list[str], typer.Argument(help="A query ('@me is:open'), or a command line.")],
) -> None:
    """Save a query, or a whole command line, under a name.

    A value starting with a command (`issue`, `sprint`…) is a command line; anything else is a
    query for `issue search`, which the TUI also shows as a view.

    [dim]acli-py alias set mine '@me is:open sort:-priority'
    acli-py alias set board-7 sprint report --board 7
    acli-py @mine --fields key,due[/]
    """
    name = name.removeprefix(ALIAS).strip()
    if not name or any(c.isspace() for c in name):
        raise fail("An alias name is one word: acli-py alias set mine '@me is:open'.")
    root: Any = ctx.find_root().command
    commands = root.list_commands(ctx) if hasattr(root, "list_commands") else []
    words = value[0].split() if len(value) == 1 else value
    command = bool(words) and words[0] in commands
    text = " ".join(value) if len(value) == 1 else shlex.join(value)
    saved_views().save(name, text, command=command)
    output.success(
        f"Saved {ALIAS}{escape(name)}: {'runs' if command else 'searches'} {escape(text)}"
    )


@alias_app.command("delete")
@guarded
def alias_delete(name: Annotated[str, typer.Argument(help="The alias to forget.")]) -> None:
    """Forget an alias (built-in views stay)."""
    if not saved_views().delete(name.removeprefix(ALIAS)):
        raise fail(f"No saved alias called {escape(name)!r}.")
    output.success(f"Forgot {ALIAS}{escape(name.removeprefix(ALIAS))}")


def alias_names() -> list[str]:
    """Return every alias as typed: '@mine'."""
    return [f"{ALIAS}{v.name}" for v in saved_views().aliases() if " " not in v.name]


# ── standup ──────────────────────────────────────────────────────────────────


@guarded
def standup(
    since: Annotated[
        str | None,
        typer.Option("--since", help="YYYY-MM-DD (default: the last working day)."),
    ] = None,
    fields: FieldsOpt = None,
    as_json: JsonOpt = False,
    out: OutputOpt = None,
) -> None:
    """Show what you changed since the last working day, and what is next for you.

    "Changed" is every issue you updated since then; "next" is your open issues, most
    important first.

    [dim]acli-py standup
    acli-py standup --output markdown | pbcopy[/]
    """
    try:
        day = date.fromisoformat(since) if since else None
    except ValueError:
        raise fail(f"{escape(str(since))!r} is not a date like 2026-10-02.") from None
    view = connect().send(Standup(date.today(), day, split(fields)))
    chosen = fmt(as_json, chosen=out)
    if chosen is Format.json:
        output.print_json(view.to_json())
        return
    if chosen in (Format.jsonl, Format.keys, Format.csv):
        _show_rows(view.rows(), view.changed, chosen)
        return
    sections = ((f"Changed since {view.since:%a %Y-%m-%d}", view.changed), ("Next", view.next))
    for title, issues in sections:
        if chosen is Format.markdown:
            output.lines([f"## {title}", ""])
            show_issues(issues, chosen, empty="Nothing.")
            output.lines([""])
        else:
            output.console.print(f"[bold]{escape(title)}[/]")
            show_issues(issues, chosen, empty="Nothing.")


def _show_rows(rows: list[dict[str, Any]], shape: IssuesView, chosen: Format) -> None:
    """Print both lists as one, a `list` column saying which each issue is in."""
    columns = [Column("List", lambda r: r["list"])] + [
        Column(c.header, lambda r, name=c.name: r[name]) for c in shape.columns
    ]
    output.emit(rows, columns, chosen)


# ── git ──────────────────────────────────────────────────────────────────────

KeyArg = Annotated[str, typer.Argument(help="Issue key, e.g. DEMO-1.")]


def _git(key: str, prefix: str | None, pick: str, as_json: bool, out: Format | None) -> None:
    names = connect().send(NameForGit(key, prefix))
    chosen = fmt(as_json, chosen=out)
    if chosen in (Format.json, Format.jsonl):
        output.emit([names.to_json()], [], chosen)
        return
    output.lines([getattr(names, pick)])


@git_app.command("branch")
@guarded
def git_branch(
    key: KeyArg,
    prefix: Annotated[
        str | None,
        typer.Option("--prefix", help="Instead of fix/ or feat/ ('' for none)."),
    ] = None,
    as_json: JsonOpt = False,
    out: OutputOpt = None,
) -> None:
    """Print a branch name for an issue: fix/DEMO-1-login-fails-on-safari.

    [dim]git switch -c "$(acli-py git branch DEMO-1)"[/]
    """
    _git(key, prefix, "branch", as_json, out)


@git_app.command("commit-msg")
@guarded
def git_commit_msg(key: KeyArg, as_json: JsonOpt = False, out: OutputOpt = None) -> None:
    """Print a Conventional Commit subject for an issue: fix: login fails on Safari (DEMO-1).

    [dim]git commit -m "$(acli-py git commit-msg DEMO-1)"[/]
    """
    _git(key, None, "commit", as_json, out)
