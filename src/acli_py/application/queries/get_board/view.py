"""`BoardView`: one board, and how it is set up."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import board_setup_json
from acli_py.domain.agile import BoardSetup


@dataclass(frozen=True)
class BoardView:
    """A board."""

    setup: BoardSetup

    def to_json(self) -> dict[str, Any]:
        """Return the board as JSON."""
        return board_setup_json(self.setup)
