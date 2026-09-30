"""The bulk engine: one kind of command, run over many issues.

Every front end that acts on several issues at once (`issue transition --jql …`, the TUI's
marked rows) hands the engine one command per issue, and the engine:

1. refuses more than `SAFETY_CAP` issues unless forced;
2. asks once, showing a preview of each issue's value now and after (`Change.preview`);
3. runs the commands a few at a time (`concurrency`), reporting each `Outcome` as it lands;
4. stops starting new ones after a failure, unless told to `keep_going`;
5. keeps the whole run as one audit record, with every issue it changed and failed on.

It returns a `Report` whose `exit_code` is 0 when everything worked, 1 when something failed.
A declined question raises `Declined` before anything runs (front ends exit 2 on it).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from acli_py.application.changes import Change, Planned, Previewable, PreviewRow, Write
from acli_py.application.messages import SearchIssues
from acli_py.domain.values import text

if TYPE_CHECKING:
    from acli_py.application.audit import AuditTrail
    from acli_py.application.behaviors.confirm import Confirm

SAFETY_CAP = 200
CONCURRENCY = 4
MAX_CONCURRENCY = 16
PREVIEW_PAGE = 100  # keys per preview search


class TooManyError(ValueError):
    """More issues than the safety cap allows, without being forced."""

    def __init__(self, count: int, cap: int) -> None:
        super().__init__(f"{count} issues is over the safety cap of {cap}.")
        self.count = count
        self.cap = cap


@dataclass(frozen=True)
class Outcome:
    """What happened to one issue: the command's result, or why it failed."""

    key: str
    ok: bool
    result: Any = None
    error: str = ""


@dataclass
class Report:
    """How a bulk run went."""

    total: int
    outcomes: list[Outcome] = field(default_factory=list)

    @property
    def succeeded(self) -> list[Outcome]:
        """Return the outcomes that worked."""
        return [o for o in self.outcomes if o.ok]

    @property
    def failed(self) -> list[Outcome]:
        """Return the outcomes that failed."""
        return [o for o in self.outcomes if not o.ok]

    @property
    def not_tried(self) -> int:
        """Return how many issues were never tried (the run stopped at a failure)."""
        return self.total - len(self.outcomes)

    @property
    def exit_code(self) -> int:
        """Return 0 when every issue worked, else 1."""
        return 0 if len(self.succeeded) == self.total else 1


def key_of(command: Any) -> str:
    """Return the issue a command works on."""
    return str(getattr(command, "key", "")).strip().upper()


def change_of(commands: Sequence[Any]) -> Change | None:
    """Return the one change the commands make together, or None when they don't say.

    Commands whose changes differ only by issue merge into one ("Move 3 issues … to Done").
    Named subjects ("a Bug in DEMO") that differ become a count ("3 issues").
    """
    if not commands or not all(isinstance(c, Write) for c in commands):
        return None
    changes = [c.change() for c in commands]
    first = changes[0]
    keys = tuple(dict.fromkeys(k for c in changes for k in c.keys))
    subject = first.subject
    if len(changes) > 1 and any(c.subject for c in changes):
        subject = subject if all(c.subject == subject for c in changes) else f"{len(keys)} issues"
    return Change(
        first.verb,
        keys,
        first.detail if all(c.detail == first.detail for c in changes) else "",
        subject=subject,
        adds=all(c.adds for c in changes),
        destructive=any(c.destructive for c in changes),
    )


class Bulk:
    """Runs one kind of command over many issues, asking once (see the module docstring)."""

    def __init__(
        self,
        send: Callable[[Any], Awaitable[Any]],
        confirm: Confirm,
        trail: AuditTrail,
        dry_run: Callable[[], bool],
    ) -> None:
        self.send = send
        self.confirm = confirm
        self.trail = trail
        self.dry_run = dry_run

    async def preview(self, commands: Sequence[Any]) -> tuple[PreviewRow, ...]:
        """Return each issue's value now and after, when the commands can say (else nothing)."""
        if commands and all(isinstance(c, Planned) for c in commands):
            return tuple(c.preview_row() for c in commands)
        if not commands or not all(isinstance(c, Previewable) for c in commands):
            return ()
        field_id = commands[0].previews()
        if field_id is None or any(c.previews() != field_id for c in commands):
            return ()
        keys = [key_of(c) for c in commands]
        found: dict[str, dict] = {}
        for start in range(0, len(keys), PREVIEW_PAGE):
            jql = f"key in ({', '.join(keys[start : start + PREVIEW_PAGE])})"
            token = None
            while True:
                page = await self.send(
                    SearchIssues(jql, token, PREVIEW_PAGE, ("summary", field_id))
                )
                found.update({i["key"]: i.get("fields") or {} for i in page.issues})
                token = page.next_token
                if not token:
                    break
        rows = []
        for command, key in zip(commands, keys, strict=True):
            fields = found.get(key, {})
            now = text(fields.get(field_id)) if key in found else "?"
            later = command.after(fields.get(field_id))
            rows.append(PreviewRow(key, text(fields.get("summary")), now, later))
        return tuple(rows)

    async def run(
        self,
        commands: Sequence[Any],
        *,
        change: Change | None = None,
        yes: bool = False,
        concurrency: int = CONCURRENCY,
        keep_going: bool = False,
        force: bool = False,
        on_outcome: Callable[[Outcome], Any] | None = None,
    ) -> Report:
        """Run `commands`, asking once about `change` (by default, the one they make together).

        Raises `TooManyError` over the safety cap unless `force`, and `Declined` when the user
        says no; nothing has run then.
        """
        if len(commands) > SAFETY_CAP and not force:
            raise TooManyError(len(commands), SAFETY_CAP)
        change = change or change_of(commands)
        if change is not None and self.confirm.will_ask(change, yes=yes) and not change.preview:
            # A preview helps; when it can't be had, the question goes on without one.
            with contextlib.suppress(Exception):
                change = replace(change, preview=await self.preview(commands))
        report = Report(len(commands))
        if change is None:
            await self._run_all(commands, report, concurrency, keep_going, on_outcome)
            return report
        async with self.confirm.batch(change, yes=yes):
            with self.trail.gather() as changes:
                await self._run_all(commands, report, concurrency, keep_going, on_outcome)
        if not self.dry_run():
            failed = {o.key: o.error for o in report.failed}
            self.trail.keep(type(commands[0]).__name__, list(changes), failed)
        return report

    async def _run_all(
        self,
        commands: Sequence[Any],
        report: Report,
        concurrency: int,
        keep_going: bool,
        on_outcome: Callable[[Outcome], Any] | None,
    ) -> None:
        gate = asyncio.Semaphore(max(1, min(concurrency, MAX_CONCURRENCY)))
        stopped = asyncio.Event()

        async def one(command: Any) -> None:
            async with gate:
                if stopped.is_set():
                    return
                try:
                    result = await self.send(command)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    outcome = Outcome(key_of(command), False, error=str(error) or repr(error))
                    if not keep_going:
                        stopped.set()
                else:
                    outcome = Outcome(key_of(command), True, result)
                report.outcomes.append(outcome)
                if on_outcome is not None:
                    on_outcome(outcome)

        await asyncio.gather(*(one(c) for c in commands))
