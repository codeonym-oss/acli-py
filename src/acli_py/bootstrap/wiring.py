"""The bus and the catalog for a site: every port's adapter, handed to the use cases."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from mediary import Mediator

from acli_py.application import commands, events, queries
from acli_py.application.audit import AuditTrail
from acli_py.application.behaviors import CACHE_SECONDS, QueryCache
from acli_py.application.bus import Bus
from acli_py.application.events.issue_changed.subscribers import Screens
from acli_py.application.ports import (
    Attachments,
    AuditLog,
    Boards,
    Comments,
    Confirmer,
    Dashboards,
    Destination,
    Filters,
    IssueEditor,
    IssueFields,
    IssueLinks,
    IssueReader,
    IssueSearch,
    IssueStore,
    People,
    Projects,
    RawApi,
    SiteFields,
    SiteLists,
    Sprints,
    Watchers,
    Workflow,
    Worklogs,
)
from acli_py.domain.jql.catalog import Catalog
from acli_py.infrastructure.audit import AuditFile
from acli_py.infrastructure.jira.agile import JiraBoards, JiraSprints
from acli_py.infrastructure.jira.catalog import JiraCatalog
from acli_py.infrastructure.jira.editor import JiraEditor, JiraWatchers
from acli_py.infrastructure.jira.fields import JiraIssueFields
from acli_py.infrastructure.jira.filters import JiraDashboards, JiraFields, JiraFilters
from acli_py.infrastructure.jira.issues import JiraIssues, JiraSearch
from acli_py.infrastructure.jira.lifecycle import JiraLinks, JiraStore
from acli_py.infrastructure.jira.parts import JiraAttachments, JiraComments, JiraWorklogs
from acli_py.infrastructure.jira.projects import (
    JiraPeople,
    JiraProjects,
    JiraRawApi,
    JiraSiteLists,
)
from acli_py.infrastructure.jira.workflow import JiraWorkflow
from acli_py.infrastructure.storage import History, Views

if TYPE_CHECKING:
    from acli_py.infrastructure.jira.site import Site

T = TypeVar("T")


class SiteResolver:
    """Hands the handlers their dependencies: the ports' adapters, else `cls()`.

    Copies go to `destination`'s site, or to `site` itself.
    """

    def __init__(self, site: Site, audit: AuditLog, destination: Site | None = None) -> None:
        self.site = site
        there = destination or site
        store = JiraStore(site.client, site.url)
        self.provided: dict[type, object] = {
            IssueReader: JiraIssues(site.client, site.url),
            IssueSearch: JiraSearch(site.client),
            Catalog: JiraCatalog(site.client),
            Workflow: JiraWorkflow(site.client),
            IssueEditor: JiraEditor(site.client),
            Watchers: JiraWatchers(site.client),
            IssueStore: store,
            IssueLinks: JiraLinks(site.client),
            Comments: JiraComments(site.client),
            Attachments: JiraAttachments(site.client),
            Worklogs: JiraWorklogs(site.client),
            Destination: store
            if there is site
            else JiraStore(there.client, there.url, elsewhere=there.url != site.url),
            AuditLog: audit,
            People: JiraPeople(site.client, lambda: site.me),
            IssueFields: JiraIssueFields(site.client, lambda: site.me),
            Projects: JiraProjects(site.client),
            Boards: JiraBoards(site.client),
            Sprints: JiraSprints(site.client),
            Filters: JiraFilters(site.client),
            SiteFields: JiraFields(site.client),
            Dashboards: JiraDashboards(site.client),
            SiteLists: JiraSiteLists(site.client),
            RawApi: JiraRawApi(site.client),
        }

    def resolve(self, cls: type[T], /) -> T:
        """Return what is provided for `cls`, else a new `cls()`."""
        if cls in self.provided:
            return self.provided[cls]  # type: ignore[return-value]
        return cls()


def build_bus(
    site: Site,
    *,
    confirmer: Confirmer | None = None,
    assume_yes: bool = False,
    audit: AuditLog | None = None,
    cache_seconds: float = CACHE_SECONDS,
    destination: Site | None = None,
) -> Bus:
    """Return a bus for `site` with every handler and subscriber registered.

    Scanning the use-case packages finds each `handler.py` and `subscribers.py`, so adding a use
    case is adding its folder. `confirmer` is how the front end asks before a change (without
    one, changes need `assume_yes`); `audit` defaults to the audit file next to the config.
    `destination` is the site clones go to, when not `site` itself.
    """
    audit = audit or AuditFile()
    resolver = SiteResolver(site, audit, destination)
    mediator = Mediator(resolver=resolver)
    mediator.scan(commands, queries, events)
    bus = Bus(
        mediator,
        site,
        audit,
        confirmer=confirmer,
        assume_yes=assume_yes,
        cache_seconds=cache_seconds,
    )
    # The subscribers work on this bus's cache, audit trail and screens.
    resolver.provided.update({QueryCache: bus.cache, AuditTrail: bus.trail, Screens: bus.listeners})
    return bus


def build_catalog(site: Site) -> Catalog:
    """Return the completion catalog for `site`."""
    return JiraCatalog(site.client)


def saved_views() -> Views:
    """Return the saved views and aliases (shared by the CLI, the shell and the TUI)."""
    return Views()


def query_history() -> History:
    """Return the queries run lately (shared by the TUI and the shell)."""
    return History()
