"""Edits to an issue's fields, as Jira takes them, and what they leave behind.

An edit sets fields outright (`{"priority": {"name": "High"}}`) or changes them with
operations (`{"labels": [{"add": "web"}, {"remove": "old"}]}`). `after` works out what an
operation leaves in a list field, so a change can be shown, and later undone, without asking
Jira again.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from acli_py.domain.values import text

# Keys that name a value in Jira's JSON, most specific first.
IDENTITY = ("accountId", "id", "key", "name", "value")


def same(a: Any, b: Any) -> bool:
    """Return whether two field values are the same thing (by id, key or name for objects)."""
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        return any(k in a and k in b and a[k] == b[k] for k in IDENTITY)
    return a == b


def after(now: Any, operations: Sequence[Mapping[str, Any]]) -> list:
    """Return a list field's value once `operations` (set, add, remove) have been applied."""
    values = list(now or [])
    for operation in operations:
        if "set" in operation:
            values = list(operation["set"] or [])
        if "add" in operation and not any(same(v, operation["add"]) for v in values):
            values.append(operation["add"])
        if "remove" in operation:
            values = [v for v in values if not same(v, operation["remove"])]
    return values


def operations_text(operations: Sequence[Mapping[str, Any]]) -> str:
    """Return operations as short text: '+web −old', or '= a, b' for a set."""
    parts = []
    for operation in operations:
        if "set" in operation:
            parts.append(f"= {text(operation['set']) or 'none'}")
        if "add" in operation:
            parts.append(f"+{text(operation['add'])}")
        if "remove" in operation:
            parts.append(f"−{text(operation['remove'])}")
    return " ".join(parts)
