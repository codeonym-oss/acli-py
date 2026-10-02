from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class SetFilterColumns(Command[Changed]):
    """Show field ids `columns` in filter `filter_id`; none goes back to the defaults."""

    filter_id: str
    columns: tuple[str, ...] = ()

    @property
    def item(self) -> str:
        """Return what the command works on, for progress lines: 'filter 10100'."""
        return f"filter {self.filter_id.strip()}"

    def change(self) -> Change:
        """Return what this command changes: 'Set filter 10100's columns to summary, status'."""
        if not self.columns:
            return Change(
                "Reset",
                (self.filter_id.strip(),),
                "columns",
                subject=f"{self.item}'s",
                noun="filter",
            )
        return Change(
            "Set",
            (self.filter_id.strip(),),
            f"columns to {', '.join(self.columns)}",
            subject=f"{self.item}'s",
            noun="filter",
        )
