"""The audit trail: one record per run of a command, however many issues it changed.

A command run on its own is recorded as soon as it has changed its issue. A bulk run
`gather`s instead: the changes its commands make are collected, and the run is recorded once
at the end, with the issues it failed on (see `acli_py.application.bulk`).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

from acli_py.application.changes import AuditRecord, Changed
from acli_py.application.ports import AuditLog


class AuditTrail:
    """Hands the `AuditLog` one `AuditRecord` per run."""

    def __init__(self, log: AuditLog) -> None:
        self.log = log
        # The changes of the bulk run in progress; tasks and worker threads inherit it.
        self._gathered: ContextVar[list[Changed] | None] = ContextVar(
            f"audit-{id(self)}", default=None
        )

    def note(self, command: str, changed: Changed) -> None:
        """Keep what `command` did: in the run being gathered, else as a record of its own."""
        gathered = self._gathered.get()
        if gathered is not None:
            gathered.append(changed)
        else:
            self.keep(command, [changed])

    @contextmanager
    def gather(self) -> Iterator[list[Changed]]:
        """Collect the changes noted inside the block, instead of recording each."""
        gathered: list[Changed] = []
        token = self._gathered.set(gathered)
        try:
            yield gathered
        finally:
            self._gathered.reset(token)

    def keep(
        self, command: str, changes: list[Changed], failed: Mapping[str, str] | None = None
    ) -> None:
        """Record one run, unless it neither changed nor failed on anything."""
        if changes or failed:
            self.log.record(AuditRecord(command, tuple(changes), datetime.now(UTC), failed or {}))
