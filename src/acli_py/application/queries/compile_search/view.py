"""`CompiledSearch`: the JQL a search runs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompiledSearch:
    """The JQL, and the smart query compiler's warnings (terms it could not place)."""

    jql: str
    warnings: tuple[str, ...] = ()
