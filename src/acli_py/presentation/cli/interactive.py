"""`acli-py tui` and `acli-py shell`: the interactive ways in."""

from __future__ import annotations

from typing import Annotated

import typer

from acli_py.application.site import Site
from acli_py.bootstrap import build_bus, build_catalog
from acli_py.domain.jql import StaticCatalog
from acli_py.domain.jql.catalog import Catalog
from acli_py.infrastructure.storage import Views
from acli_py.presentation import output
from acli_py.presentation.cli.common import DryRunOpt, Session, connect, fail, guarded


def open_site(session: Session) -> Site:
    """Return the session's site for the interactive layer, with the client made quiet.

    Plans and --debug lines would print over a full-screen UI, so the UI shows them instead.
    """
    session.client.on_plan = None
    session.client.session.hooks["response"] = []
    return session.site()


@guarded
def tui(
    query: Annotated[
        str | None,
        typer.Argument(help="A smart query or JQL to start with (default: your open work)."),
    ] = None,
    view: Annotated[
        str | None, typer.Option("--view", "-v", help="Start with a saved view, by name.")
    ] = None,
    dry_run: DryRunOpt = False,
) -> None:
    """Browse, search and change issues in a full-screen terminal UI.

    Type a query with completion as you go ([bold]Tab[/]), read issues beside the list, and
    move, assign, comment, relabel or create without leaving it. [bold]?[/] shows every key.

    [dim]acli-py tui
    acli-py tui '@me is:open sort:-priority'
    acli-py tui --view "Current sprint"
    acli-py -n tui                       # try it all; nothing is sent[/]
    """
    from acli_py.presentation.tui.app import IssueBrowser  # Textual loads only for the TUI

    session = connect(dry_run)
    views = Views()
    if view:
        found = views.find(view)
        if found is None:
            names = ", ".join(v.name for v in views.all())
            raise fail(f"No view called {view!r}. Views: {names}.")
        query = found.query
    site = open_site(session)
    app = IssueBrowser(
        build_bus(site),
        build_catalog(site.client),
        query=query or "",
        default_project=session.config.defaults.get("project"),
        views=views,
    )
    app.run()


def shell(
    dry_run: DryRunOpt = False,
) -> None:
    """Run acli-py commands at a prompt, with completion that knows your site.

    Tab completes commands, options and values: issue keys, projects, statuses, people,
    labels, and JQL or smart queries as you type them. Commands run instantly, history is
    kept (without tokens), and [bold]dry-run on[/] makes every change a preview.

    [dim]acli-py shell
    acli-py -n shell                     # start in dry-run mode[/]
    """
    import typer.main

    from acli_py.infrastructure.config import config_dir
    from acli_py.presentation.cli import app
    from acli_py.presentation.cli.common import state
    from acli_py.presentation.shell import Shell

    try:
        session = connect()
    except typer.Exit:
        catalog: Catalog = StaticCatalog()
        account = "not logged in (run: auth login)"
    else:
        catalog = build_catalog(session.client)
        account = session.account.name

    def open_tui(query: str) -> None:
        tui(query or None, view=None, dry_run=repl.dry_run)

    repl = Shell(
        typer.main.get_command(app),
        catalog,
        history=config_dir() / "shell-history",
        account=account,
        dry_run=dry_run or state.dry_run,
        open_tui=open_tui,
        output=output.errors.print,
    )
    repl.run()
