"""`ImportPlan`: what an import will change."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.changes import Change, PreviewRow

MATCHED = "(matches issues by key)"
READ_ONLY = "(skipped: read-only)"


@dataclass(frozen=True)
class ImportStep:
    """One row: the issue it names (or '#3' for a new one), the command, now → after."""

    ref: str
    summary: str
    command: Any
    now: str
    after: str
    creates: bool = False


@dataclass(frozen=True)
class ImportPlan:
    """How the columns map to fields, the rows that change something, and the others.

    `unchanged` rows match their issue already; `problems` are rows that can't be imported
    (an unknown person, an issue that isn't there), with why.
    """

    mapping: tuple[tuple[str, str], ...]
    steps: tuple[ImportStep, ...] = ()
    unchanged: tuple[str, ...] = ()
    problems: tuple[tuple[str, str], ...] = ()

    @property
    def commands(self) -> list[Any]:
        """Return the commands to run, one per row that changes something."""
        return [s.command for s in self.steps]

    def change(self) -> Change:
        """Return the question: 'Import 3 rows (DEMO-1, DEMO-2, #3)', with each row's preview."""
        rows = tuple(PreviewRow(s.ref, s.summary, s.now, s.after) for s in self.steps)
        return Change("Import", tuple(s.ref for s in self.steps), preview=rows, noun="row")

    def to_json(self) -> dict[str, Any]:
        """Return the plan as JSON."""
        return {
            "mapping": dict(self.mapping),
            "steps": [
                {"ref": s.ref, "creates": s.creates, "now": s.now, "after": s.after}
                for s in self.steps
            ],
            "unchanged": list(self.unchanged),
            "problems": [{"ref": r, "why": why} for r, why in self.problems],
        }
