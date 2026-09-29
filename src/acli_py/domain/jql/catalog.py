"""What a site offers to complete with: JQL fields, functions and the values of fields.

`Catalog` is the port completion and spelling depend on. `StaticCatalog` holds fixed data, for
tests and for when there is no connection; the Jira-backed one lives in infrastructure
(`acli_py.infrastructure.jira.catalog.JiraCatalog`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

DEFAULT_OPERATORS = ("=", "!=", "in", "not in", "is", "is not", "~", "!~", ">", ">=", "<", "<=")


@dataclass(frozen=True)
class FieldRef:
    """A field that JQL can search or sort by."""

    name: str  # what goes in the query: "status", "cf[10016]", "Story point estimate"
    display: str = ""
    operators: tuple[str, ...] = DEFAULT_OPERATORS
    orderable: bool = True
    types: tuple[str, ...] = ()
    custom: bool = False

    @property
    def label(self) -> str:
        """Return the name to show."""
        return self.display or self.name


@dataclass(frozen=True)
class FunctionRef:
    """A JQL function such as currentUser()."""

    name: str  # "currentUser()"
    is_list: bool = False
    types: tuple[str, ...] = ()


@dataclass(frozen=True)
class Value:
    """A value a field can take."""

    value: str
    display: str = ""


class Catalog(Protocol):
    """A source of completions. Implementations never raise; they return [] instead."""

    def fields(self) -> list[FieldRef]:
        """Return the fields usable in JQL."""
        ...

    def functions(self) -> list[FunctionRef]:
        """Return the JQL functions."""
        ...

    def values(self, field: str, prefix: str) -> list[Value]:
        """Return values of `field` that match `prefix`."""
        ...

    def issues(self, prefix: str) -> list[Value]:
        """Return issues (value = key, display = summary) that match `prefix`."""
        ...


# Fields every Jira Cloud site has, and the functions JQL always offers: the static catalog's
# default, and what the live one falls back to when Jira can't be asked.
_EQ = ("=", "!=", "in", "not in", "is", "is not", "was", "was in", "was not", "was not in",
       "changed")  # fmt: skip
_TEXT = ("~", "!~", "is", "is not")
_DATE = ("=", "!=", ">", ">=", "<", "<=", "is", "is not", "in", "not in", "changed")
BUILTIN_FIELDS = (
    FieldRef("project", operators=("=", "!=", "in", "not in", "is", "is not")),
    FieldRef("status", operators=_EQ),
    FieldRef("statusCategory", operators=("=", "!=", "in", "not in")),
    FieldRef("assignee", operators=_EQ),
    FieldRef("reporter", operators=_EQ),
    FieldRef("issuetype", operators=("=", "!=", "in", "not in", "is", "is not")),
    FieldRef("priority", operators=_EQ),
    FieldRef("labels", operators=("=", "!=", "in", "not in", "is", "is not")),
    FieldRef("component", operators=("=", "!=", "in", "not in", "is", "is not")),
    FieldRef("fixVersion", operators=_EQ),
    FieldRef("resolution", operators=_EQ),
    FieldRef("sprint", operators=("=", "!=", "in", "not in", "is", "is not")),
    FieldRef("parent", operators=("=", "!=", "in", "not in")),
    FieldRef("key", operators=("=", "!=", "in", "not in", ">", ">=", "<", "<=")),
    FieldRef("summary", operators=_TEXT),
    FieldRef("description", operators=_TEXT, orderable=False),
    FieldRef("comment", operators=("~", "!~"), orderable=False),
    FieldRef("text", operators=("~",), orderable=False),
    FieldRef("created", operators=_DATE),
    FieldRef("updated", operators=_DATE),
    FieldRef("resolved", operators=_DATE),
    FieldRef("due", operators=_DATE),
    FieldRef("watcher", operators=("=", "!=", "in", "not in", "is", "is not"), orderable=False),
)
BUILTIN_FUNCTIONS = (
    FunctionRef("currentUser()"),
    FunctionRef("membersOf()", is_list=True),
    FunctionRef("openSprints()", is_list=True),
    FunctionRef("closedSprints()", is_list=True),
    FunctionRef("futureSprints()", is_list=True),
    FunctionRef("startOfDay()"),
    FunctionRef("startOfWeek()"),
    FunctionRef("startOfMonth()"),
    FunctionRef("endOfDay()"),
    FunctionRef("endOfWeek()"),
    FunctionRef("endOfMonth()"),
    FunctionRef("now()"),
    FunctionRef("unreleasedVersions()", is_list=True),
    FunctionRef("releasedVersions()", is_list=True),
    FunctionRef("issueHistory()", is_list=True),
    FunctionRef("watchedIssues()", is_list=True),
    FunctionRef("updatedBy()", is_list=True),
)


def matches(text: str, prefix: str) -> bool:
    """Return whether `text` starts with `prefix`, or has a word that does (any case)."""
    if not prefix:
        return True
    text, prefix = text.lower(), prefix.lower()
    return text.startswith(prefix) or any(
        word.startswith(prefix) for word in re.split(r"[\s\-_./()\[\]]+", text)
    )


@dataclass
class StaticCatalog:
    """A catalog of fixed data."""

    field_refs: list[FieldRef] = field(default_factory=lambda: list(BUILTIN_FIELDS))
    function_refs: list[FunctionRef] = field(default_factory=lambda: list(BUILTIN_FUNCTIONS))
    field_values: dict[str, list[Value]] = field(default_factory=dict)
    issue_values: list[Value] = field(default_factory=list)

    def fields(self) -> list[FieldRef]:
        """Return the fields."""
        return self.field_refs

    def functions(self) -> list[FunctionRef]:
        """Return the functions."""
        return self.function_refs

    def values(self, field: str, prefix: str) -> list[Value]:
        """Return the stored values of `field` that match `prefix`."""
        known = self.field_values.get(field.lower(), [])
        return [v for v in known if matches(v.value, prefix) or matches(v.display, prefix)]

    def issues(self, prefix: str) -> list[Value]:
        """Return the stored issues that match `prefix`."""
        return [
            v for v in self.issue_values if matches(v.value, prefix) or matches(v.display, prefix)
        ]


# Fields whose values the site names, so a typed value can be matched to its real spelling.
SPELLED = {"status", "issuetype", "priority", "resolution", "project", "labels", "component",
           "fixversion", "assignee", "reporter", "watcher"}  # fmt: skip
USER_FIELDS = {"assignee", "reporter", "watcher"}


def _squash(text: str) -> str:
    """Return `text` lower-cased with only letters and digits: "To Do" → "todo"."""
    return re.sub(r"[^0-9a-z]", "", text.lower())


def spelling(catalog: Catalog) -> Callable[[str, str], str]:
    """Return a resolver for smart queries that fixes names from the catalog.

    `progress` becomes "In Progress" when that is the one status it can mean, and `bob` becomes
    Bob's account id. Anything ambiguous or unknown is left as typed, for Jira to judge.
    """

    def fix(field_name: str, typed: str) -> str:
        if field_name.lower() not in SPELLED:
            return typed
        found = catalog.values(field_name, typed)
        if not found and len(typed) > 3:  # "todo" finds nothing: ask for "to", match below
            found = catalog.values(field_name, typed[:2])
        low = typed.lower()
        squashed = _squash(typed)
        exact = [
            v
            for v in found
            if low in (v.value.lower(), v.display.lower())
            or squashed in (_squash(v.value), _squash(v.display))
        ]
        close = exact or [v for v in found if matches(v.display or v.value, low)]
        if len(close) == 1 or (exact and len({v.value for v in exact}) == 1):
            return close[0].value
        if field_name.lower() in USER_FIELDS and close:
            names = ", ".join(v.display or v.value for v in close[:5])
            raise ValueError(f"{field_name}: {typed!r} could be {names}; be more precise")
        return typed

    return fix
