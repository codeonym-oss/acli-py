"""Jira Software's boards and sprints, and the rules for starting a sprint."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from acli_py.domain.values import moment

if TYPE_CHECKING:
    from collections.abc import Mapping

SPRINT_WEEKS = 2


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class Board:
    """A board, and the project it is about (when it is about one)."""

    id: int
    name: str
    type: str = ""
    project: str = ""
    location: str = ""

    @classmethod
    def from_jira(cls, data: Mapping[str, Any]) -> Board:
        """Read a board from the Agile API's JSON."""
        where = _dict(data.get("location"))
        return cls(
            int(data.get("id", 0)),
            data.get("name", ""),
            data.get("type", ""),
            where.get("projectKey", ""),
            where.get("displayName", ""),
        )


@dataclass(frozen=True)
class BoardSetup:
    """How a board is set up: the filter that feeds it, its columns, how it estimates."""

    board: Board
    filter_id: str = ""
    columns: tuple[str, ...] = ()
    estimation: str = ""

    @classmethod
    def from_jira(cls, board: Mapping[str, Any], config: Mapping[str, Any]) -> BoardSetup:
        """Read a board and its configuration from the Agile API's JSON."""
        columns = _dict(config.get("columnConfig")).get("columns") or ()
        estimation = _dict(_dict(config.get("estimation")).get("field")).get("displayName", "")
        return cls(
            Board.from_jira(board),
            str(_dict(config.get("filter")).get("id", "")),
            tuple(c["name"] for c in columns if c.get("name")),
            estimation,
        )


class SprintState(StrEnum):
    """Where a sprint is in its life."""

    FUTURE = "future"
    ACTIVE = "active"
    CLOSED = "closed"


@dataclass(frozen=True)
class Sprint:
    """A sprint on a board."""

    id: int
    name: str
    state: SprintState = SprintState.FUTURE
    start: datetime | None = None
    end: datetime | None = None
    completed: datetime | None = None
    goal: str = ""
    board_id: int | None = None

    @classmethod
    def from_jira(cls, data: Mapping[str, Any]) -> Sprint:
        """Read a sprint from the Agile API's JSON."""
        board = data.get("originBoardId")
        return cls(
            int(data.get("id", 0)),
            data.get("name", ""),
            SprintState(data.get("state", "future")),
            moment(data.get("startDate")),
            moment(data.get("endDate")),
            moment(data.get("completeDate")),
            data.get("goal") or "",
            int(board) if board is not None else None,
        )

    def schedule(
        self,
        now: datetime,
        start: datetime | None = None,
        end: datetime | None = None,
        weeks: int = SPRINT_WEEKS,
    ) -> tuple[datetime, datetime]:
        """Return when the sprint runs once started: the dates given, else its own, else now.

        Without an end, it runs `weeks` from its start. Only a future sprint can start.
        """
        if self.state is not SprintState.FUTURE:
            raise ValueError(f"Sprint {self.id} is {self.state}; only a future sprint can start.")
        begin = start or self.start or now
        return begin, end or self.end or begin + timedelta(weeks=weeks)
