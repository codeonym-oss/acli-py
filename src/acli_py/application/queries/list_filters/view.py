"""`FiltersView`: a list of saved filters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import filter_json
from acli_py.domain.filters import Filter


@dataclass(frozen=True)
class FiltersView:
    """Saved filters."""

    filters: tuple[Filter, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return the filters as JSON."""
        return [filter_json(f) for f in self.filters]
