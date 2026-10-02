"""`UndoPlan`: how a recorded change will be reversed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.changes import AuditRecord, Change, PreviewRow

CHANGED_SINCE = " (changed since)"


@dataclass(frozen=True)
class UndoStep:
    """One issue put back: the command that does it, and its value now and after.

    `drifted` says the issue changed again after the recorded change: undoing sets it
    back anyway, so the user is told before agreeing.
    """

    key: str
    summary: str
    command: Any
    now: str
    after: str
    drifted: bool = False


@dataclass(frozen=True)
class UndoPlan:
    """The record to reverse, a step per issue that can be put back, and the others."""

    entry: AuditRecord
    steps: tuple[UndoStep, ...]
    skipped: tuple[tuple[str, str], ...] = ()

    @property
    def commands(self) -> list[Any]:
        """Return the commands to run, one per issue."""
        return [s.command for s in self.steps]

    @property
    def drifted(self) -> tuple[str, ...]:
        """Return the issues that changed again since the recorded change."""
        return tuple(s.key for s in self.steps if s.drifted)

    def change(self) -> Change:
        """Return the question: 'Undo DEMO-1 (change 4, EditIssue)', with each issue's preview."""
        rows = tuple(
            PreviewRow(s.key, s.summary, s.now + (CHANGED_SINCE if s.drifted else ""), s.after)
            for s in self.steps
        )
        keys = tuple(s.key for s in self.steps)
        detail = f"(change {self.entry.id}, {self.entry.command})"
        return Change("Undo", keys, detail, preview=rows)

    def to_json(self) -> dict[str, Any]:
        """Return the plan as JSON."""
        return {
            "id": self.entry.id,
            "command": self.entry.command,
            "steps": [
                {"key": s.key, "now": s.now, "after": s.after, "changedSince": s.drifted}
                for s in self.steps
            ],
            "skipped": [{"key": k, "why": why} for k, why in self.skipped],
        }
