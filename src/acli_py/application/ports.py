"""Ports: what the use cases need from the outside world, as protocols.

Handlers ask for a port by type; the composition root (`acli_py.bootstrap`) hands them the
adapter infrastructure provides. Handler tests can pass any object with the same methods.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol

from acli_py.application.changes import AuditRecord, Change
from acli_py.domain.agile import Board, BoardSetup, Sprint, SprintState
from acli_py.domain.fields import FieldInfo
from acli_py.domain.filters import Dashboard, Filter, FilterColumn
from acli_py.domain.history import HistoryEntry
from acli_py.domain.issue import (
    Attachment,
    Audience,
    Comment,
    Issue,
    Link,
    Status,
    User,
    Worklog,
)
from acli_py.domain.links import IssueLink, LinkType
from acli_py.domain.meta import IssueTypeInfo, Named, Profile, StatusInfo
from acli_py.domain.projects import Component, Project, ProjectSpec, Version
from acli_py.domain.workflow import Transition

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from pathlib import Path

    from acli_py.application.dry_run import PlannedRequest
    from acli_py.application.inputs import IssueInput


class IssueReader(Protocol):
    """Reads issues from the site."""

    def get_issue(self, key: str, fields: tuple[str, ...] = ()) -> Issue:
        """Return the issue with the detail fields, plus `fields` ('*all' for every field).

        Raises the site's not-found error when there is no such issue (or it is hidden).
        """
        ...

    def browse_url(self, key: str) -> str:
        """Return the issue's page on the site."""
        ...

    def history(self, key: str) -> list[HistoryEntry]:
        """Return the issue's changelog, oldest first."""
        ...


class IssueSearch(Protocol):
    """Finds issues with JQL."""

    def search(
        self, jql: str, fields: tuple[str, ...], *, limit: int | None, token: str | None = None
    ) -> tuple[list[Issue], str | None]:
        """Return up to `limit` issues (None: all) with `fields`, from `token` on.

        Also returns the token that goes on from there, or None when there are no more.
        """
        ...

    def count(self, jql: str) -> int:
        """Return how many issues match (Jira's estimate)."""
        ...

    def filter_jql(self, filter_id: str) -> str:
        """Return the JQL the saved filter runs."""
        ...

    def problems(self, jql: str) -> list[str]:
        """Return what the site finds wrong with `jql`; none when it is valid."""
        ...


class Workflow(Protocol):
    """Moves issues through their workflow."""

    def status(self, key: str) -> Status | None:
        """Return the issue's status now."""
        ...

    def transitions(self, key: str) -> list[Transition]:
        """Return the transitions available on the issue now."""
        ...

    def transition(
        self, key: str, transition_id: str, fields: Mapping[str, Any], comment: str
    ) -> None:
        """Apply a transition, setting `fields` (as Jira takes them) and adding `comment`."""
        ...


class IssueEditor(Protocol):
    """Changes an issue's fields, and reads them first so the change can be undone."""

    def values(self, key: str, field_ids: tuple[str, ...]) -> dict[str, Any]:
        """Return the fields' values now, as Jira has them (None for an empty field)."""
        ...

    def edit(
        self,
        key: str,
        fields: Mapping[str, Any],
        update: Mapping[str, Any],
        *,
        notify: bool = True,
    ) -> None:
        """Set `fields` and apply `update`'s operations, emailing watchers unless not `notify`."""
        ...

    def assign(self, key: str, account_id: str | None) -> None:
        """Assign the issue (None: to nobody, '-1': to the project's default assignee)."""
        ...


class Watchers(Protocol):
    """Who watches an issue."""

    def watching(self, key: str, account_id: str) -> bool:
        """Return whether the person watches the issue."""
        ...

    def watch(self, key: str, account_id: str, *, watch: bool = True) -> None:
        """Make the person watch the issue, or (not `watch`) stop."""
        ...

    def watchers(self, key: str) -> list[User]:
        """Return who watches the issue."""
        ...


class IssueFields(Protocol):
    """Turns what someone typed for an issue (a CSV row, a JSON object) into Jira's fields."""

    def build(self, row: Mapping[str, Any], *, creating: bool = False) -> dict[str, Any]:
        """Return the fields `row` sets, as Jira takes them: names resolved to ids.

        Friendly keys ('summary', 'labels', 'due') and field names ('Story point estimate')
        both work; values are text, lists, or Markdown for the description.
        """
        ...

    def field_of(self, column: str) -> str:
        """Return the id of the field a column fills; raise `ValueError` when none matches."""
        ...

    def fields_for(self, wanted: IssueInput, *, creating: bool = False) -> dict[str, Any]:
        """Return the fields `wanted` sets, as Jira takes them (a new issue's when `creating`)."""
        ...

    def field_values(self, assignments: tuple[str, ...]) -> dict[str, Any]:
        """Return {field id: value} for 'NAME=VALUE' and 'NAME:=JSON' assignments."""
        ...


class IssueStore(Protocol):
    """Creates, deletes and archives whole issues."""

    def create(self, fields: Mapping[str, Any], update: Mapping[str, Any]) -> str:
        """Create an issue from `fields` and `update` (as Jira takes them); return its key."""
        ...

    def delete(self, key: str, *, subtasks: bool = False) -> None:
        """Delete the issue for good (with its subtasks, when `subtasks`; else Jira refuses)."""
        ...

    def archive(self, key: str, *, archive: bool = True) -> None:
        """Archive the issue, or (not `archive`) restore it; raise `ValueError` when refused."""
        ...


class IssueLinks(Protocol):
    """Links between issues on the site."""

    def link_types(self) -> tuple[LinkType, ...]:
        """Return the kinds of link the site offers."""
        ...

    def links_of(self, key: str) -> tuple[Link, ...]:
        """Return the issue's links, read from its side."""
        ...

    def get_link(self, link_id: str) -> IssueLink:
        """Return the link with this id."""
        ...

    def link(self, link: IssueLink, comment: Mapping[str, Any] | None = None) -> None:
        """Store `link`, adding `comment` (an ADF document) to its outward issue."""
        ...

    def unlink(self, link_id: str) -> None:
        """Remove the link with this id."""
        ...


class Comments(Protocol):
    """Comments on issues. Bodies go in as ADF documents and come out as Markdown."""

    def comments(
        self, key: str, *, newest_first: bool = False, limit: int | None = None
    ) -> list[Comment]:
        """Return the issue's comments, oldest first unless `newest_first`."""
        ...

    def comment(self, key: str, comment_id: str) -> Comment:
        """Return one comment."""
        ...

    def add(self, key: str, body: Mapping[str, Any], audience: Audience | None = None) -> str:
        """Add a comment, kept to `audience` when given; return its id."""
        ...

    def update(
        self,
        key: str,
        comment_id: str,
        body: Mapping[str, Any],
        audience: Audience | None = None,
        *,
        notify: bool = False,
    ) -> None:
        """Replace a comment's body (and audience), emailing watchers when `notify`."""
        ...

    def delete(self, key: str, comment_id: str) -> None:
        """Delete a comment."""
        ...

    def audiences(self, project: str | None = None) -> list[Audience]:
        """Return who a comment can be kept to: `project`'s roles, or else the site's groups."""
        ...


class Attachments(Protocol):
    """Files attached to issues."""

    def attachments(self, key: str) -> list[Attachment]:
        """Return the issue's attachments."""
        ...

    def attachment(self, attachment_id: str) -> Attachment:
        """Return one attachment's details."""
        ...

    def upload(self, key: str, path: Path) -> list[Attachment]:
        """Attach the file at `path` to the issue; return what was attached."""
        ...

    def download(self, attachment_id: str, dest: Path) -> int:
        """Save the attachment's content to `dest`; return its size in bytes."""
        ...

    def delete(self, attachment_id: str) -> None:
        """Delete the attachment."""
        ...


class Worklogs(Protocol):
    """Time logged on issues."""

    def worklogs(self, key: str) -> list[Worklog]:
        """Return the work logged on the issue."""
        ...

    def worklog(self, key: str, worklog_id: str) -> Worklog:
        """Return one worklog."""
        ...

    def log(
        self,
        key: str,
        spent: str,
        comment: Mapping[str, Any] | None = None,
        started: datetime | None = None,
        remaining: str = "",
    ) -> str:
        """Log `spent` ('1h 30m') on the issue, setting the remaining estimate when given.

        Returns the worklog's id.
        """
        ...

    def delete(self, key: str, worklog_id: str) -> None:
        """Delete a worklog."""
        ...


class Destination(Protocol):
    """Where copies of issues go: this site, or (`elsewhere`) another one the user is on."""

    @property
    def elsewhere(self) -> bool:
        """Return whether copies go to another site."""
        ...

    @property
    def url(self) -> str:
        """Return the site's address."""
        ...

    def create(self, fields: Mapping[str, Any], update: Mapping[str, Any]) -> str:
        """Create an issue there; return its key."""
        ...

    def web_link(self, key: str, url: str, title: str) -> None:
        """Add a web link to an issue there."""
        ...


class People(Protocol):
    """Finds the people a user means."""

    def account_id(self, who: str) -> str:
        """Return the account id of the one person `who` names: '@me', an email, a name, an id.

        Raises `ValueError` when nobody, or more than one person, matches.
        """
        ...

    def search(self, text: str, *, limit: int) -> list[Profile]:
        """Return up to `limit` people whose name or email contain `text`."""
        ...

    def profile(self, who: str) -> Profile:
        """Return the profile (with groups) of the one person `who` names, '@me' included."""
        ...

    def assignable(self, key: str, text: str) -> list[User]:
        """Return people (not apps) who can be assigned issue `key`, matching `text`."""
        ...


class SiteLists(Protocol):
    """The site's own lists: statuses, priorities, resolutions and issue types."""

    def statuses(self) -> list[StatusInfo]:
        """Return every status."""
        ...

    def priorities(self) -> list[Named]:
        """Return the priorities, highest first."""
        ...

    def resolutions(self) -> list[Named]:
        """Return the resolutions."""
        ...

    def issue_types(self, project: str | None = None) -> list[IssueTypeInfo]:
        """Return the issue types: all of them, or those project `project` uses."""
        ...


class RawApi(Protocol):
    """Any REST endpoint, as the site answers it."""

    def request(self, method: str, path: str, params: Mapping[str, Any], body: Any = None) -> Any:
        """Send the request and return the JSON answer (None for an empty one)."""
        ...

    def is_write(self, method: str, path: str) -> bool:
        """Return whether the request would change something."""
        ...


class Projects(Protocol):
    """The site's projects."""

    def projects(self, *, query: str | None, status: str, limit: int | None) -> list[Project]:
        """Return projects by key, whose key or name match `query`, in `status`.

        `status` is 'live', 'archived' or 'deleted' (in the trash).
        """
        ...

    def recent(self) -> list[Project]:
        """Return up to 20 projects the user viewed lately, most recent first."""
        ...

    def project(self, key: str) -> Project:
        """Return the project with its lead, issue types, components and versions."""
        ...

    def components(self, key: str) -> list[Component]:
        """Return the project's components."""
        ...

    def versions(self, key: str) -> list[Version]:
        """Return the project's versions."""
        ...

    def shared_configuration(self, key: str) -> dict[str, int]:
        """Return the type, category and scheme ids a project copying `key`'s setup takes.

        Keys are Jira's project fields ('permissionScheme', 'categoryId'); `projectTypeKey` is
        among them. Raises `ValueError` for a team-managed project: its setup is its own.
        """
        ...

    def create(self, spec: ProjectSpec, lead: str, shared: Mapping[str, Any]) -> str:
        """Create the project `spec` describes, led by account `lead`; return its id.

        `shared` holds the type and schemes copied from another project (see
        `shared_configuration`); a template and shared schemes don't go together.
        """
        ...

    def update(self, key: str, spec: ProjectSpec, lead: str | None) -> None:
        """Change what `spec` gives, and the lead to account `lead` when given."""
        ...

    def delete(self, key: str, *, permanent: bool = False) -> None:
        """Move the project to the trash, or (`permanent`) delete it for good."""
        ...

    def archive(self, key: str) -> None:
        """Archive the project."""
        ...

    def restore(self, key: str) -> None:
        """Bring the project back from the trash or the archive."""
        ...


class Boards(Protocol):
    """Jira Software's boards."""

    def boards(
        self,
        *,
        name: str | None = None,
        type: str | None = None,
        project: str | None = None,
        filter_id: str | None = None,
        order: str | None = None,
        private: bool = False,
        limit: int | None = None,
    ) -> list[Board]:
        """Return the boards matching what is given."""
        ...

    def board(self, board_id: int) -> BoardSetup:
        """Return the board and how it is set up."""
        ...

    def projects(self, board_id: int, *, limit: int | None) -> list[Project]:
        """Return the projects the board shows."""
        ...

    def backlog(
        self, board_id: int, jql: str | None, fields: tuple[str, ...], *, limit: int | None
    ) -> list[Issue]:
        """Return the issues in the board's backlog (narrowed by `jql`), with `fields`."""
        ...

    def create(self, name: str, type: str, filter_id: int, project: str | None, owner: str) -> int:
        """Create a board fed by a filter, in `project`, else owned by account `owner`.

        Returns its id.
        """
        ...

    def delete(self, board_id: int) -> None:
        """Delete the board (its issues and filter stay)."""
        ...


class Sprints(Protocol):
    """Sprints, and the issues in them."""

    def sprints(
        self, board_id: int, states: tuple[SprintState, ...], *, limit: int | None
    ) -> list[Sprint]:
        """Return the board's sprints in `states` (all when none)."""
        ...

    def sprint(self, sprint_id: int) -> Sprint:
        """Return the sprint."""
        ...

    def issues(
        self, sprint_id: int, jql: str | None, fields: tuple[str, ...], *, limit: int | None
    ) -> list[Issue]:
        """Return the issues in the sprint (narrowed by `jql`), with `fields`."""
        ...

    def create(
        self,
        board_id: int,
        name: str,
        start: datetime | None,
        end: datetime | None,
        goal: str | None,
    ) -> int:
        """Create a future sprint on the board; return its id."""
        ...

    def update(
        self,
        sprint_id: int,
        *,
        name: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        goal: str | None = None,
        state: SprintState | None = None,
    ) -> None:
        """Change what is given (None: leave it)."""
        ...

    def delete(self, sprint_id: int) -> None:
        """Delete the sprint; its issues go back to the backlog."""
        ...

    def move(self, keys: tuple[str, ...], sprint_id: int | None) -> None:
        """Move issues into the sprint, or (None) back to the backlog."""
        ...


class Filters(Protocol):
    """Saved filters. Share permissions go in as Jira takes them."""

    def mine(self) -> list[Filter]:
        """Return the user's own filters."""
        ...

    def favourites(self) -> list[Filter]:
        """Return the filters the user starred."""
        ...

    def search(
        self, *, name: str | None, owner: str | None, project: str | None, limit: int | None
    ) -> list[Filter]:
        """Return the filters the user can see: by name, owner (account id), project (key)."""
        ...

    def filter(self, filter_id: str) -> Filter:
        """Return the filter, with who it is shared with."""
        ...

    def create(
        self,
        name: str,
        jql: str,
        description: str | None,
        favourite: bool,
        shares: tuple[Mapping[str, Any], ...] | None,
    ) -> str:
        """Save a filter; return its id."""
        ...

    def update(
        self,
        filter_id: str,
        *,
        name: str,
        jql: str | None = None,
        description: str | None = None,
        shares: tuple[Mapping[str, Any], ...] | None = None,
        edit_shares: tuple[Mapping[str, Any], ...] | None = None,
    ) -> None:
        """Change the filter; Jira needs its `name` even when that stays."""
        ...

    def delete(self, filter_id: str) -> None:
        """Delete the filter."""
        ...

    def star(self, filter_id: str, *, star: bool = True) -> None:
        """Add the filter to the user's favourites, or (not `star`) take it out."""
        ...

    def give(self, filter_id: str, account_id: str) -> None:
        """Make account `account_id` the filter's owner."""
        ...

    def columns(self, filter_id: str) -> list[FilterColumn]:
        """Return the columns the filter shows."""
        ...

    def set_columns(self, filter_id: str, fields: tuple[str, ...]) -> None:
        """Show these field ids as the filter's columns; none goes back to the default ones."""
        ...


class SiteFields(Protocol):
    """The site's fields, and its custom fields' lifecycle."""

    def fields(self) -> list[FieldInfo]:
        """Return every field."""
        ...

    def trashed(self, query: str | None) -> list[FieldInfo]:
        """Return the custom fields in the trash, matching `query`."""
        ...

    def create(self, name: str, type: str, searcher: str | None, description: str | None) -> str:
        """Create a custom field; return its id."""
        ...

    def update(
        self, field_id: str, *, name: str | None, description: str | None, searcher: str | None
    ) -> None:
        """Change what is given of a custom field."""
        ...

    def trash(self, field_id: str) -> None:
        """Move a custom field to the trash."""
        ...

    def restore(self, field_id: str) -> None:
        """Bring a custom field back from the trash."""
        ...


class Dashboards(Protocol):
    """Dashboards."""

    def search(self, *, name: str | None, owner: str | None, limit: int | None) -> list[Dashboard]:
        """Return the dashboards matching a name and owner (account id)."""
        ...

    def dashboard(self, dashboard_id: str) -> Dashboard:
        """Return the dashboard."""
        ...


class CurrentSite(Protocol):
    """The site a bus works on, as front ends see it: where, who, and whether it's a dry run."""

    url: str
    account_id: str
    display_name: str

    @property
    def dry_run(self) -> bool:
        """Return whether writes are only planned."""
        ...

    @property
    def me(self) -> str:
        """Return the user's account id (asking the site once, if need be)."""
        ...

    def browse(self, key: str) -> str:
        """Return an issue's page on the site."""
        ...

    @property
    def on_plan(self) -> Callable[[PlannedRequest], Any] | None:
        """Return what is told of each write a dry run plans instead of sending."""
        ...

    @on_plan.setter
    def on_plan(self, listener: Callable[[PlannedRequest], Any] | None) -> None: ...


class Confirmer(Protocol):
    """Asks the user whether to go ahead with a change; each front end brings its own."""

    async def confirm(self, change: Change) -> bool:
        """Return whether the user agrees to `change`.

        May raise `Declined` with a reason instead, when there is no way to ask.
        """
        ...


class AuditLog(Protocol):
    """Keeps a record of every change made."""

    def record(self, entry: AuditRecord) -> None:
        """Add `entry` to the log."""
        ...

    def entries(self) -> list[AuditRecord]:
        """Return every record, oldest first, each with its `id`."""
        ...
