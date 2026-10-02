"""`FilterView`: one saved filter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import filter_json
from acli_py.domain.filters import Filter


@dataclass(frozen=True)
class FilterView:
    """A saved filter."""

    filter: Filter

    def to_json(self) -> dict[str, Any]:
        """Return the filter as JSON."""
        return filter_json(self.filter)
