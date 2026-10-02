"""`FilterColumnsView`: the columns a filter shows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import column_json
from acli_py.domain.filters import FilterColumn


@dataclass(frozen=True)
class FilterColumnsView:
    """A filter's columns, in order."""

    columns: tuple[FilterColumn, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return the columns as JSON."""
        return [column_json(c) for c in self.columns]
