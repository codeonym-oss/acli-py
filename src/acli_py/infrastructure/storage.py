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
    """A named query."""

    name: str
    query: str
    builtin: bool = False


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
    """The built-in views plus the user's, in `views.json`."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_dir() / "views.json"

    def saved(self) -> list[View]:
        """Return the user's views."""
        data = _read(self.path, {})
        if not isinstance(data, dict):
            return []
        return [View(str(k), str(v)) for k, v in data.items()]

    def all(self) -> list[View]:
        """Return the built-in views, then the user's."""
        return [*BUILTIN_VIEWS, *self.saved()]

    def find(self, name: str) -> View | None:
        """Return the view called `name` (any case)."""
        return next((v for v in self.all() if v.name.lower() == name.strip().lower()), None)

    def save(self, name: str, query: str) -> None:
        """Save (or replace) a view."""
        name = name.strip()
        if not name:
            raise ValueError("a view needs a name")
        if any(v.name.lower() == name.lower() for v in BUILTIN_VIEWS):
            raise ValueError(f"{name!r} is a built-in view; pick another name")
        data = {v.name: v.query for v in self.saved() if v.name.lower() != name.lower()}
        data[name] = query.strip()
        _write(self.path, data)

    def delete(self, name: str) -> bool:
        """Delete a saved view; return whether there was one."""
        kept = {v.name: v.query for v in self.saved() if v.name.lower() != name.strip().lower()}
        if len(kept) == len(self.saved()):
            return False
        _write(self.path, kept)
        return True


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
