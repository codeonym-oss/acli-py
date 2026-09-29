"""What a site offers to complete with: JQL fields, functions and the values of fields.

`JiraCatalog` asks Jira the way its own search box does (`/jql/autocompletedata` and
`/jql/autocompletedata/suggestions`), so custom fields and site-specific values complete too.
Answers are cached for a few minutes, and a failed call completes with nothing rather than
raising: completion must never get in the way of typing. `StaticCatalog` holds fixed data, for
tests and for when there is no connection.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from acli_py.client import API, JiraError

if TYPE_CHECKING:
    from collections.abc import Callable

    from acli_py.client import JiraClient

DEFAULT_OPERATORS = ("=", "!=", "in", "not in", "is", "is not", "~", "!~", ">", ">=", "<", "<=")
TTL = 300.0


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


def _flag(value: Any) -> bool:
    return str(value).lower() == "true"


def _plain(html: str) -> str:
    """Drop the <b> highlighting Jira puts in suggestion display names."""
    return re.sub(r"</?b>", "", html or "")


class JiraCatalog:
    """A catalog that asks Jira, caching every answer for `ttl` seconds."""

    def __init__(self, client: JiraClient, *, ttl: float = TTL) -> None:
        self.client = client
        self.ttl = ttl
        self._cache: dict[tuple[str, ...], tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def _cached(self, key: tuple[str, ...], load: Callable[[], Any], fallback: Any) -> Any:
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        try:
            value = load()
        except (JiraError, ValueError, KeyError, TypeError, AttributeError):
            return fallback
        with self._lock:
            self._cache[key] = (now, value)
        return value

    def clear(self) -> None:
        """Forget everything cached."""
        with self._lock:
            self._cache.clear()

    def _reference(self) -> dict:
        return self._cached(
            ("reference",), lambda: self.client.get(f"{API}/jql/autocompletedata"), {}
        )

    def fields(self) -> list[FieldRef]:
        """Return the site's JQL fields (the built-in list if Jira can't be asked)."""
        refs = []
        seen: set[str] = set()
        for item in self._reference().get("visibleFieldNames", []):
            name = item.get("value") or ""
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            refs.append(
                FieldRef(
                    name=name,
                    display=item.get("displayName", ""),
                    operators=tuple(item.get("operators") or DEFAULT_OPERATORS),
                    orderable=_flag(item.get("orderable")),
                    types=tuple(item.get("types") or ()),
                    custom=bool(item.get("cfid")),
                )
            )
        return refs or list(BUILTIN_FIELDS)

    def functions(self) -> list[FunctionRef]:
        """Return the site's JQL functions."""
        refs = [
            FunctionRef(
                name=item.get("value") or item.get("displayName", ""),
                is_list=_flag(item.get("isList")),
                types=tuple(item.get("types") or ()),
            )
            for item in self._reference().get("visibleFunctionNames", [])
        ]
        return [r for r in refs if r.name] or list(BUILTIN_FUNCTIONS)

    def values(self, field: str, prefix: str) -> list[Value]:
        """Return Jira's suggestions for a value of `field` starting with `prefix`."""

        def load() -> list[Value]:
            data = self.client.get(
                f"{API}/jql/autocompletedata/suggestions", fieldName=field, fieldValue=prefix
            )
            return [
                Value(str(r["value"]), _plain(r.get("displayName", "")))
                for r in data.get("results", [])
                if r.get("value") is not None
            ]

        return self._cached(("values", field.lower(), prefix.lower()), load, [])

    def issues(self, prefix: str) -> list[Value]:
        """Return issues matching `prefix`, from Jira's issue picker."""

        def load() -> list[Value]:
            data = self.client.get(f"{API}/issue/picker", query=prefix, showSubTasks="true")
            found: dict[str, Value] = {}
            for section in data.get("sections", []):
                for issue in section.get("issues", []):
                    key = issue.get("key")
                    if key and key not in found:
                        summary = issue.get("summaryText") or _plain(issue.get("summary", ""))
                        found[key] = Value(key, summary)
            return list(found.values())

        return self._cached(("issues", prefix.lower()), load, [])


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
