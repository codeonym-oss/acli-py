"""Accounts, settings and connections: how front ends sign in and open a site.

The settings file, the token store and the HTTP client are infrastructure; front ends reach
them only through these functions, and get back a `Site` to build a bus on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from acli_py.infrastructure import credentials
from acli_py.infrastructure.config import SETTINGS, Account, Config, config_dir
from acli_py.infrastructure.jira.client import JiraClient, normalize_url, site_host
from acli_py.infrastructure.jira.site import Site

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from acli_py.application.dry_run import PlannedRequest

__all__ = [
    "SETTINGS",
    "Account",
    "Config",
    "Site",
    "forget_token",
    "normalize_url",
    "open_site",
    "shell_history_path",
    "sign_in",
    "site_host",
    "token_of",
    "token_store",
]


def token_of(account: Account) -> str | None:
    """Return the API token saved for `account`, if any."""
    return credentials.load_token(account.name, account.token_backend)


def open_site(
    account: Account,
    token: str,
    *,
    dry_run: bool = False,
    on_response: Callable[[Any], Any] | None = None,
    on_plan: Callable[[PlannedRequest], Any] | None = None,
) -> Site:
    """Open a connection to `account`'s site; close it with `Site.close`.

    `on_response` hears of every HTTP response (for --debug), `on_plan` of every write a dry
    run plans instead of sending.
    """
    client = JiraClient(account.url, account.email, token, dry_run=dry_run,
                        on_response=on_response, on_plan=on_plan)  # fmt: skip
    return Site(client, account.url, account.account_id, account.display_name)


def sign_in(site: str, email: str, token: str) -> Account:
    """Check the token with the site, store it, and make the account the active one.

    Raises `SignInError` when the site rejects it.
    """
    url = normalize_url(site)
    client = JiraClient(url, email, token, retries=2)
    try:
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
    return account


def forget_token(account: Account) -> None:
    """Delete the account's API token from wherever it is stored."""
    credentials.delete_token(account.name)


def token_store(account: Account) -> str:
    """Return where the account's token is kept, in words."""
    return credentials.describe(account.token_backend)


def shell_history_path() -> Path:
    """Return where the shell keeps its history."""
    return config_dir() / "shell-history"
