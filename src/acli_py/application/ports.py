"""Ports: what the use cases need from the outside world, as protocols.

Handlers ask for a port by type; the composition root (`acli_py.bootstrap`) hands them the
adapter infrastructure provides. Handler tests can pass any object with the same methods.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from acli_py.application.changes import AuditRecord, Change
from acli_py.domain.issue import Issue, Status
from acli_py.domain.workflow import Transition


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
