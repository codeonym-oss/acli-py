"""`JiraBoards` and `JiraSprints`: Jira Software's Agile API, over the client."""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING, Any

from acli_py.domain.agile import Board, BoardSetup, Sprint
from acli_py.domain.issue import Issue
from acli_py.domain.projects import Project
from acli_py.infrastructure.jira.client import AGILE

if TYPE_CHECKING:
    from datetime import datetime

    from acli_py.domain.agile import SprintState
    from acli_py.infrastructure.jira.client import JiraClient

MOVE_PAGE = 50  # issues per move request, as the Agile API allows


def stamp(moment: datetime | None) -> str | None:
    """Return a moment as the Agile API takes it: '2026-10-05T09:00:00.000Z' (UTC)."""
    if moment is None:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


class JiraBoards:
    """Reads and changes boards through a `JiraClient`."""

    def __init__(self, client: JiraClient) -> None:
        self.client = client

    def boards(
        self,
        *,
        name: str | None = None,
        type: str | None = None,
        project: str | None = None,
        filter_id: str | None = None,
        order: str | None = None,
        private: bool = False,
        limit: int | None = None,
    ) -> list[Board]:
        """Return the boards matching what is given."""
        found = self.client.paged(
            f"{AGILE}/board",
            limit=limit,
            name=name,
            type=type,
            projectKeyOrId=project,
            filterId=filter_id,
            orderBy=order,
            includePrivate="true" if private else None,
        )
        return [Board.from_jira(b) for b in found]

    def board(self, board_id: int) -> BoardSetup:
        """Return the board and its configuration."""
        board = self.client.get(f"{AGILE}/board/{board_id}")
        return BoardSetup.from_jira(
            board, self.client.get(f"{AGILE}/board/{board_id}/configuration")
        )

    def projects(self, board_id: int, *, limit: int | None) -> list[Project]:
        """Return the board's projects."""
        found = self.client.paged(f"{AGILE}/board/{board_id}/project", limit=limit)
        return [Project.from_jira(p) for p in found]

    def backlog(
        self, board_id: int, jql: str | None, fields: tuple[str, ...], *, limit: int | None
    ) -> list[Issue]:
        """Return the backlog's issues."""
        return _issues(self.client, f"{AGILE}/board/{board_id}/backlog", jql, fields, limit)

    def create(self, name: str, type: str, filter_id: int, project: str | None, owner: str) -> int:
        """Create the board."""
        location = (
            {"type": "project", "projectKeyOrId": project}
            if project
            else {"type": "user", "projectKeyOrId": owner}
        )
        body = {"name": name, "type": type, "filterId": filter_id, "location": location}
        return _id(self.client.post(f"{AGILE}/board", body))

    def delete(self, board_id: int) -> None:
        """Delete the board."""
        self.client.delete(f"{AGILE}/board/{board_id}")


class JiraSprints:
    """Reads and changes sprints through a `JiraClient`."""

    def __init__(self, client: JiraClient) -> None:
        self.client = client

    def sprints(
        self, board_id: int, states: tuple[SprintState, ...], *, limit: int | None
    ) -> list[Sprint]:
        """Return the board's sprints."""
        found = self.client.paged(
            f"{AGILE}/board/{board_id}/sprint", limit=limit, state=",".join(states) or None
        )
        return [Sprint.from_jira(s) for s in found]

    def sprint(self, sprint_id: int) -> Sprint:
        """Return the sprint."""
        return Sprint.from_jira(self.client.get(f"{AGILE}/sprint/{sprint_id}"))

    def issues(
        self, sprint_id: int, jql: str | None, fields: tuple[str, ...], *, limit: int | None
    ) -> list[Issue]:
        """Return the sprint's issues."""
        return _issues(self.client, f"{AGILE}/sprint/{sprint_id}/issue", jql, fields, limit)

    def create(
        self,
        board_id: int,
        name: str,
        start: datetime | None,
        end: datetime | None,
        goal: str | None,
    ) -> int:
        """Create a future sprint."""
        body = {
            "name": name,
            "originBoardId": board_id,
            "startDate": stamp(start),
            "endDate": stamp(end),
            "goal": goal,
        }
        return _id(self.client.post(f"{AGILE}/sprint", _given(body)))

    def update(
        self,
        sprint_id: int,
        *,
        name: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        goal: str | None = None,
        state: SprintState | None = None,
    ) -> None:
        """Change the sprint (a partial update)."""
        body = {
            "name": name,
            "startDate": stamp(start),
            "endDate": stamp(end),
            "goal": goal,
            "state": state.value if state else None,
        }
        self.client.post(f"{AGILE}/sprint/{sprint_id}", _given(body))

    def delete(self, sprint_id: int) -> None:
        """Delete the sprint."""
        self.client.delete(f"{AGILE}/sprint/{sprint_id}")

    def move(self, keys: tuple[str, ...], sprint_id: int | None) -> None:
        """Move the issues, a page at a time."""
        path = f"{AGILE}/sprint/{sprint_id}/issue" if sprint_id else f"{AGILE}/backlog/issue"
        for start in range(0, len(keys), MOVE_PAGE):
            self.client.post(path, {"issues": list(keys[start : start + MOVE_PAGE])})


def _given(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if v is not None}


def _id(created: Any) -> int:
    """Return the id Jira gave something new (0 in a dry run, where nothing was made)."""
    value = str((created or {}).get("id", ""))
    return int(value) if value.isdigit() else 0


def _issues(
    client: JiraClient, path: str, jql: str | None, fields: tuple[str, ...], limit: int | None
) -> list[Issue]:
    found = client.paged(path, key="issues", limit=limit, jql=jql, fields=",".join(fields))
    return [Issue.from_jira(i) for i in found]
