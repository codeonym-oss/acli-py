"""What a dry run sends instead of a change: nothing, and a plan of what it would have sent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# A stand-in id for things a dry run pretends to create.
DRY_RUN_ID = "DRY-RUN"


@dataclass
class PlannedRequest:
    """A write that a dry run did not send."""

    method: str
    path: str
    params: dict[str, Any] = field(default_factory=dict)
    body: Any = None
    files: list[str] = field(default_factory=list)
