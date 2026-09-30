"""What commands change: declared before they run, reported after, recorded for later.

- `Change`: what a command is about to do ("Move DEMO-1 to Done"). A command that changes Jira
  says so by having a `change()` method (the `Write` protocol); the `Confirm` behavior shows it
  and asks before the command runs. Over many issues it carries a preview: one `PreviewRow`
  per issue, its value now and after (commands that can say so are `Previewable`).
- `Changed`: what a command did to one issue, its fields before and after. The `Announce`
  behavior publishes it as `IssueChanged`, and the audit log keeps it (for undo, later).
- `AuditRecord`: one run of a command, over one issue or many, as the audit log keeps it.
- `Declined`: the user said no, or there was no way to ask them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

SHOWN_KEYS = 5


@dataclass(frozen=True)
class Change:
    """What a command is about to change: `verb` the `keys`, then `detail`.

    `Change("Move", ("DEMO-1",), "to Done")` reads "Move DEMO-1 to Done".
    """

    verb: str
    keys: tuple[str, ...]
    detail: str = ""
    preview: tuple[PreviewRow, ...] = field(default=(), compare=False)

    def covers(self, other: Change) -> bool:
        """Return whether agreeing to this change also agrees to `other`."""
        return (self.verb, self.detail) == (other.verb, other.detail) and set(other.keys) <= set(
            self.keys
        )

    def __str__(self) -> str:
        """Return the change as a sentence, naming at most a few keys."""
        if len(self.keys) == 1:
            what = self.keys[0]
        else:
            shown = ", ".join(self.keys[:SHOWN_KEYS]) + ("…" if len(self.keys) > SHOWN_KEYS else "")
            what = f"{len(self.keys)} issues ({shown})"
        return " ".join(part for part in (self.verb, what, self.detail) if part)


@dataclass(frozen=True)
class PreviewRow:
    """One issue in a change's preview: what the field holds now, and will hold after."""

    key: str
    summary: str
    now: str
    after: str


@runtime_checkable
class Write(Protocol):
    """A command that changes Jira, and says how before it runs."""

    def change(self) -> Change:
        """Return what running this command changes."""
        ...


@runtime_checkable
class Previewable(Protocol):
    """A `Write` command that can say which field it sets, and to what, for a preview."""

    def previews(self) -> tuple[str, str]:
        """Return the id of the field this command sets, and the value it sets it to."""
        ...


@dataclass(frozen=True)
class Changed:
    """What a command did to one issue: the fields it touched, before and after."""

    key: str
    before: Mapping[str, Any] = field(default_factory=dict)
    after: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditRecord:
    """One run of a command, as the audit log keeps it: every issue it changed, and failed on."""

    command: str
    changes: tuple[Changed, ...]
    at: datetime
    failed: Mapping[str, str] = field(default_factory=dict)

    @property
    def keys(self) -> tuple[str, ...]:
        """Return the issues the run touched, or tried to."""
        return tuple(c.key for c in self.changes) + tuple(self.failed)


class Declined(Exception):  # noqa: N818 - it reads as what happened: the change was declined
    """The user said no to a change, or there was no way to ask them."""

    def __init__(self, reason: str = "Cancelled.") -> None:
        super().__init__(reason)
