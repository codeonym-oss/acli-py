"""Ports: what the use cases need from the outside world, as protocols.

Handlers ask for a port by type; the composition root (`acli_py.bootstrap`) hands them the
adapter infrastructure provides. Handler tests can pass any object with the same methods.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol

from acli_py.application.changes import AuditRecord, Change
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
from acli_py.domain.workflow import Transition

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path


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
