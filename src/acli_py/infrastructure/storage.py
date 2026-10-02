"""Saved views and query history, kept next to the config and shared by the TUI and shell."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from acli_py.infrastructure.config import config_dir

if TYPE_CHECKING:
    from pathlib import Path

HISTORY_SIZE = 500


@dataclass(frozen=True)
class View:
    """A named query, or (`command`) a named command line: an alias, `acli-py @name`."""

    name: str
    query: str
    builtin: bool = False
    command: bool = False


BUILTIN_VIEWS = (
    View("My open work", "is:mine is:open sort:-priority,-updated", True),
    View("Current sprint", "is:sprint sort:status,-priority", True),
    View("Reported by me", "is:reported is:open", True),
    View("Watching", "is:watching is:open", True),
    View("Recently updated", "updated:7d", True),
    View("Overdue", "is:overdue sort:due", True),
    View("Unassigned", "is:unassigned is:open sort:-priority", True),
)


def _read(path: Path, default: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


class Views:
    """The built-in views plus the user's, in `views.json`.

    The file maps each name to a query, or to `{"command": "issue search …"}` for an alias of
    a whole command line. The TUI shows the queries; `acli-py @name` runs either.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_dir() / "views.json"

    def _stored(self) -> list[View]:
        data = _read(self.path, {})
        if not isinstance(data, dict):
            return []
        found = []
        for name, value in data.items():
            if isinstance(value, dict) and isinstance(value.get("command"), str):
                found.append(View(str(name), value["command"], command=True))
            elif isinstance(value, str):
                found.append(View(str(name), value))
        return found

    def saved(self) -> list[View]:
        """Return the user's views (queries only)."""
        return [v for v in self._stored() if not v.command]

    def all(self) -> list[View]:
        """Return the built-in views, then the user's."""
        return [*BUILTIN_VIEWS, *self.saved()]

    def aliases(self) -> list[View]:
        """Return everything `acli-py @name` runs: the views, then the command lines."""
        return [*BUILTIN_VIEWS, *self._stored()]

    def find(self, name: str) -> View | None:
        """Return the view called `name` (any case)."""
        return next((v for v in self.all() if v.name.lower() == name.strip().lower()), None)

    def find_alias(self, name: str) -> View | None:
        """Return the view or command line called `name` (any case)."""
        return next((v for v in self.aliases() if v.name.lower() == name.strip().lower()), None)

    def save(self, name: str, query: str, *, command: bool = False) -> None:
        """Save (or replace) a view, or (`command`) an alias of a command line."""
        name = name.strip()
        if not name:
            raise ValueError("a view needs a name")
        if any(v.name.lower() == name.lower() for v in BUILTIN_VIEWS):
            raise ValueError(f"{name!r} is a built-in view; pick another name")
        kept = [v for v in self._stored() if v.name.lower() != name.lower()]
        _write(self.path, {**_data(kept), name: _value(query.strip(), command)})

    def delete(self, name: str) -> bool:
        """Delete a saved view or alias; return whether there was one."""
        stored = self._stored()
        kept = [v for v in stored if v.name.lower() != name.strip().lower()]
        if len(kept) == len(stored):
            return False
        _write(self.path, _data(kept))
        return True


def _value(query: str, command: bool) -> object:
    return {"command": query} if command else query


def _data(views: list[View]) -> dict[str, object]:
    return {v.name: _value(v.query, v.command) for v in views}


class History:
    """Queries run recently, newest last, without repeats."""

    def __init__(self, path: Path | None = None, size: int = HISTORY_SIZE) -> None:
        self.path = path or config_dir() / "query-history.json"
        self.size = size

    def load(self) -> list[str]:
        """Return the queries, oldest first."""
        data = _read(self.path, [])
        return [str(q) for q in data] if isinstance(data, list) else []

    def add(self, query: str) -> None:
        """Remember a query (moving it to the end if it was there)."""
        query = query.strip()
        if not query:
            return
        items = [q for q in self.load() if q != query] + [query]
        # History is a convenience: never fail a search over it.
        with contextlib.suppress(OSError):
            _write(self.path, items[-self.size :])
