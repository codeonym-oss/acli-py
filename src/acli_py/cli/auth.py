"""`aj auth`: log in with API tokens, keep several accounts, switch between them."""

from __future__ import annotations

import sys
from typing import Annotated

import typer
from rich.markup import escape
from rich.prompt import IntPrompt, Prompt

from acli_py import credentials, output
from acli_py.cli.common import JsonOpt, connect, fail, guarded
from acli_py.client import JiraClient, normalize_url
from acli_py.config import Account, Config
from acli_py.output import Column, Format

app = typer.Typer(help="Log in, log out, and switch between Jira accounts.", no_args_is_help=True)

TOKEN_URL = "https://id.atlassian.com/manage-profile/security/api-tokens"


@app.command()
@guarded
def login(
    site: Annotated[
        str | None,
        typer.Option("--site", "-s", help="Jira site, e.g. your-team.atlassian.net."),
    ] = None,
    email: Annotated[
        str | None, typer.Option("--email", "-e", help="Your Atlassian account email.")
    ] = None,
    token: Annotated[
        str | None,
        typer.Option("--token", "-t", help="API token. Prefer --token-stdin or the prompt."),
    ] = None,
    token_stdin: Annotated[
        bool, typer.Option("--token-stdin", help="Read the API token from standard input.")
    ] = False,
) -> None:
    """Check an API token against the site, store it securely and make it the active account.

    Logging in again with the same site and email replaces its token.
    """
    site = site or Prompt.ask("Jira site", console=output.errors)
    email = email or Prompt.ask("Account email", console=output.errors)
    if token_stdin:
        token = sys.stdin.read()
    if not token:
        output.info(f"Create a token at {TOKEN_URL}")
        token = Prompt.ask("API token", password=True, console=output.errors)
    token, email, url = token.strip(), email.strip(), normalize_url(site)
    if not token:
        raise fail("The API token is empty.")

    client = JiraClient(url, email, token, retries=2)
    try:
        with output.errors.status("Checking the token with Jira…"):
            me = client.myself()
    finally:
        client.close()

    account = Account(
        url=url,
        email=email,
        account_id=me.get("accountId", ""),
        display_name=me.get("displayName", ""),
        time_zone=me.get("timeZone", ""),
    )
    account.token_backend = credentials.save_token(account.name, token)
    config = Config.load()
    config.accounts[account.name] = account
    config.active = account.name
    config.save()
    output.success(
        f"Logged in to [bold]{escape(account.host)}[/] as [bold]{escape(account.display_name)}[/]"
    )
    output.info(f"Token stored in {escape(credentials.describe(account.token_backend))}")


@app.command()
@guarded
def logout(
    account: Annotated[
        str | None,
        typer.Argument(help="Account to remove (email@site, email or site). Default: active."),
    ] = None,
    everyone: Annotated[bool, typer.Option("--all", help="Log out of every account.")] = False,
) -> None:
    """Forget an account and delete its API token."""
    config = Config.load()
    if everyone:
        chosen = list(config.accounts.values())
    elif account:
        chosen = _match(config, account)
    else:
        chosen = [config.account] if config.account else []
    if not chosen:
        raise fail("Not logged in.")
    for gone in chosen:
        credentials.delete_token(gone.name)
        del config.accounts[gone.name]
        output.success(f"Logged out of {escape(gone.name)}")
    if config.active not in config.accounts:
        config.active = next(iter(config.accounts), None)
        if config.active:
            output.info(f"Active account is now {escape(config.active)}")
    config.save()


@app.command()
@guarded
def status(
    check: Annotated[
        bool, typer.Option("--check", help="Also verify the active token with Jira.")
    ] = False,
    as_json: JsonOpt = False,
) -> None:
    """List saved accounts; the active one is marked ●."""
    config = Config.load()
    if not config.accounts:
        raise fail("Not logged in. Run [bold]aj auth login[/].")
    accounts = list(config.accounts.values())
    if as_json:
        output.print_json(
            [
                {
                    "account": a.name,
                    "site": a.url,
                    "email": a.email,
                    "name": a.display_name,
                    "accountId": a.account_id,
                    "active": a.name == config.active,
                }
                for a in accounts
            ]
        )
        return
    output.emit(
        accounts,
        [
            Column("", lambda a: "●" if a.name == config.active else "", style="green"),
            Column("Site", lambda a: a.host, style="bold"),
            Column("Email", lambda a: a.email),
            Column("Name", lambda a: a.display_name),
            Column("Token", lambda a: a.token_backend, style="dim"),
        ],
        Format.table,
    )
    if check:
        session = connect()
        with output.errors.status("Checking the token…"):
            me = session.client.myself()
        output.success(
            f"Token for {escape(session.account.name)} is valid ({me.get('displayName')})"
        )


@app.command()
@guarded
def switch(
    account: Annotated[
        str | None, typer.Argument(help="Account to activate (email@site, email or site).")
    ] = None,
    site: Annotated[str | None, typer.Option("--site", "-s", help="Pick by site.")] = None,
    email: Annotated[str | None, typer.Option("--email", "-e", help="Pick by email.")] = None,
) -> None:
    """Make another saved account the active one (asks which when there are several)."""
    config = Config.load()
    if not config.accounts:
        raise fail("Not logged in. Run [bold]aj auth login[/].")
    if account:
        matches = _match(config, account)
    elif site or email:
        matches = config.find(site, email)
    else:
        matches = list(config.accounts.values())
    if not matches:
        raise fail("No saved account matches. See [bold]aj auth status[/].")
    if len(matches) > 1:
        if not sys.stdin.isatty():
            raise fail("Several accounts match; name one, e.g. [bold]aj auth switch EMAIL@SITE[/].")
        for n, a in enumerate(matches, 1):
            mark = "●" if a.name == config.active else " "
            output.errors.print(f"  [cyan]{n}[/] {mark} {escape(a.name)}")
        pick = IntPrompt.ask(
            "Switch to",
            choices=[str(n) for n in range(1, len(matches) + 1)],
            console=output.errors,
        )
        matches = [matches[pick - 1]]
    config.active = matches[0].name
    config.save()
    output.success(f"Active account: [bold]{escape(config.active)}[/]")


def _match(config: Config, text: str) -> list[Account]:
    wanted = text.lower()
    exact = [a for a in config.accounts.values() if a.name.lower() == wanted]
    if exact:
        return exact
    return [a for a in config.accounts.values() if wanted in (a.email.lower(), a.host.lower())]
