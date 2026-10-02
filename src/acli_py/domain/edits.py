"""Edits to an issue's fields, as Jira takes them, and what they leave behind.

An edit sets fields outright (`{"priority": {"name": "High"}}`) or changes them with
operations (`{"labels": [{"add": "web"}, {"remove": "old"}]}`). `after` works out what an
operation leaves in a list field, so a change can be shown, and later undone, without asking
Jira again.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from acli_py.domain import adf
from acli_py.domain.values import text

# Keys that name a value in Jira's JSON, most specific first.
IDENTITY = ("accountId", "id", "key", "name", "value")


def same(a: Any, b: Any) -> bool:
    """Return whether two field values are the same thing (by id, key or name for objects)."""
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        return any(k in a and k in b and a[k] == b[k] for k in IDENTITY)
    return a == b


def identities(value: Any) -> set[str]:
    """Return what names a value: each id, key or name of an object, else the value as text."""
    if isinstance(value, Mapping):
        return {str(value[k]) for k in IDENTITY if value.get(k) not in (None, "")}
    return {str(value)}


def equal(a: Any, b: Any) -> bool:
    """Return whether two values of a field hold the same thing, however Jira spelled them.

    Empty values (None, '', []) are equal; lists are equal whatever their order; an object
    equals text that is one of its ids or names ({"name": "Done"} and "Done"); documents
    (ADF) are equal when their text is.
    """
    if adf.is_adf(a) or adf.is_adf(b):
        return text(a) == text(b)
    if a in (None, "", [], {}) or b in (None, "", [], {}):
        return a in (None, "", [], {}) and b in (None, "", [], {})
    if isinstance(a, list) or isinstance(b, list):
        left, right = (
            list(a) if isinstance(a, list) else [a],
            list(b) if isinstance(b, list) else [b],
        )
        return len(left) == len(right) and all(any(equal(x, y) for y in right) for x in left)
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        return same(a, b) or a == b
    return bool(identities(a) & identities(b))


def as_input(value: Any) -> Any:
    """Return a value Jira sent, in the shape it takes back: objects by their id or name.

    `{"self": …, "id": "3", "name": "Medium"}` becomes `{"id": "3"}`; a document (ADF) or a
    value with nothing that names it is kept whole.
    """
    if isinstance(value, list):
        return [as_input(v) for v in value]
    if isinstance(value, Mapping):
        name = next((k for k in IDENTITY if value.get(k) not in (None, "")), None)
        return {name: value[name]} if name else dict(value)
    return value


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
