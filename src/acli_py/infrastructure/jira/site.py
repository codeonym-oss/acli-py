"""`Site`: an open client to one Jira site, and who is using it (the `CurrentSite` port)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from acli_py.application.dry_run import PlannedRequest
    from acli_py.infrastructure.jira.client import JiraClient


@dataclass
class Site:
    """An open client plus who is using it."""

    client: JiraClient
    url: str
    account_id: str = ""
    display_name: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def dry_run(self) -> bool:
        """Return whether writes are only planned."""
        return self.client.dry_run

    @property
    def me(self) -> str:
        """Return the user's account id, asking Jira once if it isn't known."""
        with self._lock:
            if not self.account_id:
                profile = self.client.myself()
                self.account_id = profile.get("accountId", "")
                self.display_name = self.display_name or profile.get("displayName", "")
            return self.account_id

    def browse(self, key: str) -> str:
        """Return an issue's web URL."""
        return f"{self.url}/browse/{key}"

    @property
    def planned(self) -> list[PlannedRequest]:
        """Return the writes a dry run planned instead of sending."""
        return self.client.planned

    @property
    def on_plan(self) -> Callable[[PlannedRequest], Any] | None:
        """Return what is told of each write a dry run plans."""
        return self.client.on_plan

    @on_plan.setter
    def on_plan(self, listener: Callable[[PlannedRequest], Any] | None) -> None:
        self.client.on_plan = listener

    def quiet(self) -> None:
        """Stop printing plans and --debug lines (a full-screen UI shows them itself)."""
        self.client.on_plan = None
        self.client.session.hooks["response"] = []

    def close(self) -> None:
        """Close the connection."""
        self.client.close()
