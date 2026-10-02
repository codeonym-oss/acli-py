"""`JqlProblems`: what is wrong with a query."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JqlProblems:
    """The site's complaints, in its words."""

    problems: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        """Return whether there is anything wrong."""
        return bool(self.problems)
