"""The composition root: the one place that wires infrastructure into the application.

Front ends (the CLI, the shell, the TUI) never build Jira clients, catalogs or handlers
themselves; they ask for a ready bus or catalog here. Swapping an adapter (a fake Jira in
tests, another backend later) means changing this module only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from mediary import Mediator

from acli_py.application import commands, events, handlers, queries
from acli_py.application.behaviors import CACHE_SECONDS
from acli_py.application.bus import Bus
from acli_py.application.ports import IssueReader
from acli_py.application.site import Site
from acli_py.infrastructure.jira.catalog import JiraCatalog
from acli_py.infrastructure.jira.client import JiraClient
from acli_py.infrastructure.jira.issues import JiraIssues

if TYPE_CHECKING:
    from acli_py.domain.jql.catalog import Catalog

T = TypeVar("T")


class SiteResolver:
    """Hands the handlers their dependencies: the ports' adapters, the `Site`, else `cls()`."""

    def __init__(self, site: Site) -> None:
        self.site = site
        self.provided: dict[type, object] = {
            Site: site,
            JiraClient: site.client,
            IssueReader: JiraIssues(site.client, site.url),
        }

    def resolve(self, cls: type[T], /) -> T:
        """Return what is provided for `cls`, else a new `cls()`."""
        if cls in self.provided:
            return self.provided[cls]  # type: ignore[return-value]
        return cls()


def build_bus(site: Site, *, cache_seconds: float = CACHE_SECONDS) -> Bus:
    """Return a bus for `site` with every handler and subscriber registered.

    Scanning the use-case packages finds each `handler.py` and `subscribers.py`, so adding a use
    case is adding its folder.
    """
    mediator = Mediator(resolver=SiteResolver(site))
    mediator.scan(handlers, commands, queries, events)
    return Bus(mediator, site, cache_seconds=cache_seconds)


def build_catalog(client: JiraClient) -> Catalog:
    """Return the completion catalog for the site `client` talks to."""
    return JiraCatalog(client)
