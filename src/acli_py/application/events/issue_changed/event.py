from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from mediary.cqrs import Event, event


@event
@dataclass(frozen=True)
class IssueChanged(Event):
    """A command changed an issue (or, in a dry run, would have).

    `what` is the command's name; `before` and `after` hold the fields it touched, when the
    command reports them.
    """

    key: str
    what: str
    dry_run: bool = False
    before: Mapping[str, Any] = field(default_factory=dict, compare=False)
    after: Mapping[str, Any] = field(default_factory=dict, compare=False)
