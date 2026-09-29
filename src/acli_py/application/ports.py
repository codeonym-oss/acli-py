"""Ports: what the use cases need from the outside world, as protocols.

Handlers ask for a port by type; the composition root (`acli_py.bootstrap`) hands them the
adapter infrastructure provides. Handler tests can pass any object with the same methods.
"""

from __future__ import annotations

from typing import Protocol

from acli_py.domain.issue import Issue


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
