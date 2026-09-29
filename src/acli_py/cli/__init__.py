"""The `aj` command line (also installed as `acli-py`)."""

from __future__ import annotations

from typing import Annotated

import typer

from acli_py import __version__, output
from acli_py.cli import agile, auth, config_cmd, filters, issue, issue_parts, misc, project
from acli_py.cli.common import close_clients, state

app = typer.Typer(
    name="aj",
    help="A friendly command line for Jira Cloud. Every change can be previewed with "
    "[bold]--dry-run[/].",
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)

issue.app.add_typer(issue_parts.comment_app, name="comment")
issue.app.add_typer(issue_parts.link_app, name="link")
issue.app.add_typer(issue_parts.attachment_app, name="attachment")
issue.app.add_typer(issue_parts.watcher_app, name="watcher")
issue.app.add_typer(issue_parts.worklog_app, name="worklog")

app.add_typer(auth.app, name="auth", rich_help_panel="Setup")
app.add_typer(config_cmd.app, name="config", rich_help_panel="Setup")
app.add_typer(issue.app, name="issue", rich_help_panel="Work")
app.add_typer(project.app, name="project", rich_help_panel="Work")
app.add_typer(agile.board_app, name="board", rich_help_panel="Work")
app.add_typer(agile.sprint_app, name="sprint", rich_help_panel="Work")
app.add_typer(filters.filter_app, name="filter", rich_help_panel="Work")
app.add_typer(misc.dashboard_app, name="dashboard", rich_help_panel="Work")
app.add_typer(filters.field_app, name="field", rich_help_panel="Site")
app.add_typer(misc.user_app, name="user", rich_help_panel="Site")
app.add_typer(misc.meta_app, name="meta", rich_help_panel="Site")
app.command("api", rich_help_panel="Site")(misc.api)
# acli's name for issues, for muscle memory.
app.add_typer(issue.app, name="workitem", hidden=True)


def version_callback(value: bool) -> None:
    """Print the version and exit."""
    if value:
        output.console.print(f"acli-py {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Preview every change instead of making it (also ACLI_PY_DRY_RUN=1).",
        ),
    ] = False,
    account: Annotated[
        str | None,
        typer.Option("--account", help="Use this saved account (email@site) for one command."),
    ] = None,
    debug: Annotated[
        bool, typer.Option("--debug", help="Print every HTTP request Jira answers.")
    ] = False,
    version: Annotated[
        bool | None,
        typer.Option(
            "--version", "-V", callback=version_callback, is_eager=True, help="Show the version."
        ),
    ] = None,
) -> None:
    """Start with [bold]aj auth login[/], then use [bold]aj issue[/], [bold]aj sprint[/]…."""
    state.dry_run, state.debug, state.account = dry_run, debug, account
    state.clients.clear()
    ctx.call_on_close(close_clients)
