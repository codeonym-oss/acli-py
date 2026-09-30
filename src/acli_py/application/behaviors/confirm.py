"""Asks before a command changes anything, once per change the user agrees to."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from mediary import Next

from acli_py.application.changes import Change, Declined, Write
from acli_py.application.ports import Confirmer


class Confirm:
    """Shows each `Write` command's `Change` and runs it only if the user agrees.

    Dry runs never ask: nothing is sent. `assume_yes` (--yes) never asks either. Front ends
    running one change over many issues call `approve` (or `batch`) with the whole change first,
    so the user is asked once, not once per issue. Without a `confirmer` there is no way to ask,
    so changes are declined unless already agreed to.
    """

    def __init__(
        self,
        confirmer: Confirmer | None,
        dry_run: Callable[[], bool],
        *,
        assume_yes: bool = False,
    ) -> None:
        self.confirmer = confirmer
        self.dry_run = dry_run
        self.assume_yes = assume_yes
        self.approved: list[Change] = []

    def will_ask(self, *, yes: bool = False) -> bool:
        """Return whether approving a change now would ask the user."""
        return not (yes or self.assume_yes or self.dry_run())

    async def approve(self, change: Change, *, yes: bool = False) -> None:
        """Ask about `change` unless `yes`; afterwards, commands it covers run without asking.

        Raises `Declined` when the user says no, or cannot be asked.
        """
        if self.will_ask(yes=yes):
            if self.confirmer is None:
                raise Declined(f"{change}? Refusing: there is no way to ask.")
            if not await self.confirmer.confirm(change):
                raise Declined()
        self.approved.append(change)

    def forget(self, change: Change) -> None:
        """Ask again next time `change` comes up."""
        if change in self.approved:
            self.approved.remove(change)

    @asynccontextmanager
    async def batch(self, change: Change, *, yes: bool = False) -> AsyncIterator[None]:
        """Ask once about `change`, for the commands sent inside the block."""
        await self.approve(change, yes=yes)
        try:
            yield
        finally:
            self.forget(change)

    async def handle(self, message: object, next: Next[Any], /) -> Any:
        """Ask about the command's change unless it is agreed to already, then run it."""
        if isinstance(message, Write):
            change = message.change()
            if not any(agreed.covers(change) for agreed in self.approved):
                await self.approve(change)
                self.forget(change)
        return await next()
