"""The composition root: the one place that wires infrastructure into the application.

Front ends (the CLI, the shell, the TUI) never build Jira clients, catalogs or handlers
themselves: they open a site (`accounts`) and ask for a ready bus or catalog (`wiring`).
Swapping an adapter (a fake Jira in tests, another backend later) means changing this package.
"""

from acli_py.bootstrap.accounts import (
    SETTINGS,
    Account,
    Config,
    Site,
    forget_token,
    normalize_url,
    open_site,
    shell_history_path,
    sign_in,
    site_host,
    token_of,
    token_store,
)
from acli_py.bootstrap.wiring import (
    History,
    SiteResolver,
    Views,
    build_bus,
    build_catalog,
    query_history,
    saved_views,
)

__all__ = [
    "SETTINGS",
    "Account",
    "Config",
    "History",
    "Site",
    "SiteResolver",
    "Views",
    "build_bus",
    "build_catalog",
    "forget_token",
    "normalize_url",
    "open_site",
    "query_history",
    "saved_views",
    "shell_history_path",
    "sign_in",
    "site_host",
    "token_of",
    "token_store",
]
