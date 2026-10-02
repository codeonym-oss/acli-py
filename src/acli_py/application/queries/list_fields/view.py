"""`FieldsView`: the site's fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import field_json
from acli_py.domain.fields import FieldInfo


@dataclass(frozen=True)
class FieldsView:
    """Fields."""

    fields: tuple[FieldInfo, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return the fields as JSON."""
        return [field_json(f) for f in self.fields]
