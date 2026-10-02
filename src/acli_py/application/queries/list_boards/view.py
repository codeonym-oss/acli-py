"""`BoardsView`: a list of boards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import board_json
from acli_py.domain.agile import Board


@dataclass(frozen=True)
class BoardsView:
    """Boards."""

    boards: tuple[Board, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return the boards as JSON."""
        return [board_json(b) for b in self.boards]
