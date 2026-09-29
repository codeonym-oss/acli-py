"""The completion catalog backed by Jira itself.

`JiraCatalog` asks Jira the way its own search box does (`/jql/autocompletedata` and
`/jql/autocompletedata/suggestions`), so custom fields and site-specific values complete too.
Answers are cached for a few minutes, and a failed call completes with nothing rather than
raising: completion must never get in the way of typing.
"""

from __future__ import annotations

import re
import threading
import time
from typing import TYPE_CHECKING, Any

from acli_py.domain.jql.catalog import (
    BUILTIN_FIELDS,
    BUILTIN_FUNCTIONS,
    DEFAULT_OPERATORS,
    FieldRef,
    FunctionRef,
    Value,
)
from acli_py.infrastructure.jira.client import API, JiraError

if TYPE_CHECKING:
    from collections.abc import Callable

    from acli_py.infrastructure.jira.client import JiraClient

TTL = 300.0


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
