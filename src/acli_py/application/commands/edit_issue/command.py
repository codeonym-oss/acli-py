from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed
from acli_py.domain import edits
from acli_py.domain.values import text

SHOWN_VALUE = 30  # characters of a value shown in the question


@command
@dataclass(frozen=True)
class EditIssue(Command[Changed]):
    """Set fields of an issue and apply operations to others, in one edit.

    `fields` are set outright and `update` holds Jira's operations (`{"labels": [{"add":
    "web"}]}`), both in the shape Jira takes them. An `assignee` among the fields goes through
    Jira's assign endpoint, which needs less permission than an edit. `notify` emails the
    watchers.
    """

    key: str
    fields: Mapping[str, Any] = field(default_factory=dict, compare=False)
    update: Mapping[str, Sequence[Mapping[str, Any]]] = field(default_factory=dict, compare=False)
    notify: bool = True

    @classmethod
    def setting(cls, key: str, field_id: str, value: Any) -> EditIssue:
        """Return the edit that sets one field."""
        return cls(key, {field_id: value})

    @classmethod
    def labelling(cls, key: str, add: Iterable[str] = (), remove: Iterable[str] = ()) -> EditIssue:
        """Return the edit that adds and removes labels, keeping the others."""
        operations = [{"add": label} for label in add] + [{"remove": label} for label in remove]
        return cls(key, update={"labels": operations} if operations else {})

    @property
    def touched(self) -> tuple[str, ...]:
        """Return the ids of the fields this edit changes."""
        return tuple(dict.fromkeys([*self.fields, *self.update]))

    def change(self) -> Change:
        """Return what this command changes: 'Edit DEMO-1: priority → High, labels +web'."""
        parts = [f"{f} → {shorten(text(v)) or 'none'}" for f, v in self.fields.items()]
        parts += [f"{f} {edits.operations_text(ops)}" for f, ops in self.update.items()]
        return Change("Edit", (self.key.strip().upper(),), ": " + ", ".join(parts) if parts else "")

    def previews(self) -> str | None:
        """Return the field this edit changes, for a preview; None when it changes several."""
        return self.touched[0] if len(self.touched) == 1 else None

    def after(self, now: Any) -> str:
        """Return the field's value after the edit, as text."""
        field_id = self.touched[0]
        if field_id in self.update:
            now = edits.after(now, self.update[field_id])
        if field_id in self.fields:
            now = self.fields[field_id]
        return text(now)


def shorten(value: str) -> str:
    """Return `value` cut to a length that fits in a question."""
    return value if len(value) <= SHOWN_VALUE else value[: SHOWN_VALUE - 1] + "…"
