"""The Jira site the interactive front ends work on, as the handlers see it."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

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
