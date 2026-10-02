from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mediary.cqrs import Command, command


@command
@dataclass(frozen=True)
class CallApi(Command[Any]):
    """Send `method` to `path` with `params` and the JSON `body`; return the JSON answer."""

    method: str
    path: str
    params: tuple[tuple[str, tuple[str, ...]], ...] = ()
    body: Any = field(default=None, compare=False)

    @property
    def key(self) -> str:
        """Return what the audit log keeps the call under: 'POST /rest/api/3/issue'."""
        return f"{self.method.upper()} {self.path}"
