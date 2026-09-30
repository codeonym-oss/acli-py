"""Workflows: the transitions that move an issue from one status to another."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from acli_py.domain.issue import Status

if TYPE_CHECKING:
    from collections.abc import Iterable


class NoSuchTransitionError(ValueError):
    """The issue cannot move where it was asked to, from its current status."""


@dataclass(frozen=True)
class Transition:
    """A move available on an issue now: 'Start work' takes it to 'In Progress'."""

    id: str
    name: str
    to: Status | None = None

    @classmethod
    def from_jira(cls, data: Any) -> Transition | None:
        """Return the transition in `data`, or None."""
        if not isinstance(data, dict) or not data.get("id"):
            return None
        return cls(str(data["id"]), str(data.get("name") or ""), Status.from_jira(data.get("to")))

    @property
    def target(self) -> str:
        """Return the status this transition leads to (its own name when Jira doesn't say)."""
        return self.to.name if self.to else self.name


def pick(available: Iterable[Transition], wanted: str, key: str) -> Transition:
    """Return the transition `wanted` names: by id, else target status, else transition name.

    Raises `NoSuchTransitionError`, listing what is available, when none matches.
    """
    options = list(available)
    exact, lowered = wanted.strip(), wanted.strip().lower()
    for matches in (
        lambda t: t.id == exact,
        lambda t: t.to is not None and t.to.name.lower() == lowered,
        lambda t: t.name.lower() == lowered,
    ):
        found = next((t for t in options if matches(t)), None)
        if found is not None:
            return found
    names = ", ".join(f"{t.name} → {t.target}" for t in options)
    raise NoSuchTransitionError(
        f"{key} cannot move to {wanted!r} from its current status. Available: {names or 'none'}"
    )
