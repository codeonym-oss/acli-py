"""The JSON shapes views share: users, statuses, issues' parts, projects, boards, filters….

Keys are camelCase, as in Jira's own JSON; dates are ISO strings; missing values are null.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from acli_py.domain.agile import Board, BoardSetup, Sprint
from acli_py.domain.fields import FieldInfo
from acli_py.domain.filters import Dashboard, Filter, FilterColumn
from acli_py.domain.issue import Attachment, Comment, IssueRef, Link, Status, User, Worklog
from acli_py.domain.projects import Component, Project, Version


def iso(value: date | None) -> str | None:
    """Return a date or moment as ISO text, or None."""
    return value.isoformat() if value else None


def status_json(status: Status | None) -> dict | None:
    """Return a status as JSON."""
    return {"name": status.name, "category": status.category.value} if status else None


def user_json(user: User | None) -> dict | None:
    """Return a person as JSON."""
    if user is None:
        return None
    return {"accountId": user.account_id, "name": user.name, "email": user.email or None}


def ref_json(ref: IssueRef | None) -> dict | None:
    """Return a reference to another issue as JSON."""
    if ref is None:
        return None
    return {"key": ref.key, "summary": ref.summary, "status": status_json(ref.status)}


def comment_json(comment: Comment) -> dict[str, Any]:
    """Return a comment as JSON, its body as Markdown."""
    return {"id": comment.id, "author": user_json(comment.author),
            "created": iso(comment.created), "updated": iso(comment.updated),
            "visibleTo": comment.visible_to or None, "body": comment.body}  # fmt: skip


def link_json(link: Link) -> dict[str, Any]:
    """Return a link, from its issue's side, as JSON."""
    return {"id": link.id, "type": link.type, "direction": link.direction.value,
            "phrase": link.phrase, "issue": ref_json(link.issue)}  # fmt: skip


def attachment_json(attachment: Attachment) -> dict[str, Any]:
    """Return an attachment as JSON."""
    return {"id": attachment.id, "filename": attachment.filename, "size": attachment.size,
            "mimeType": attachment.mime_type or None, "author": user_json(attachment.author),
            "created": iso(attachment.created)}  # fmt: skip


def worklog_json(worklog: Worklog) -> dict[str, Any]:
    """Return a worklog as JSON."""
    return {"id": worklog.id, "author": user_json(worklog.author),
            "started": iso(worklog.started), "timeSpent": worklog.spent,
            "timeSpentSeconds": worklog.seconds, "comment": worklog.comment}  # fmt: skip


def component_json(component: Component) -> dict[str, Any]:
    """Return a project's component as JSON."""
    return {"id": component.id, "name": component.name, "lead": user_json(component.lead),
            "description": component.description or None}  # fmt: skip


def version_json(version: Version) -> dict[str, Any]:
    """Return a project's version as JSON."""
    return {"id": version.id, "name": version.name, "released": version.released,
            "archived": version.archived, "startDate": iso(version.start),
            "releaseDate": iso(version.release),
            "description": version.description or None}  # fmt: skip


def project_json(project: Project) -> dict[str, Any]:
    """Return a project as JSON, with its issue types, components and versions when known."""
    return {"id": project.id, "key": project.key, "name": project.name,
            "projectTypeKey": project.type or None, "style": project.style or None,
            "lead": user_json(project.lead), "category": project.category or None,
            "url": project.url or None, "description": project.description or None,
            "issueTypes": list(project.issue_types),
            "components": [component_json(c) for c in project.components],
            "versions": [version_json(v) for v in project.versions]}  # fmt: skip


def board_json(board: Board) -> dict[str, Any]:
    """Return a board as JSON."""
    return {"id": board.id, "name": board.name, "type": board.type,
            "projectKey": board.project or None, "location": board.location or None}  # fmt: skip


def board_setup_json(setup: BoardSetup) -> dict[str, Any]:
    """Return a board and how it is set up as JSON."""
    return {**board_json(setup.board), "filterId": setup.filter_id or None,
            "columns": list(setup.columns), "estimation": setup.estimation or None}  # fmt: skip


def sprint_json(sprint: Sprint) -> dict[str, Any]:
    """Return a sprint as JSON."""
    return {"id": sprint.id, "name": sprint.name, "state": sprint.state.value,
            "startDate": iso(sprint.start), "endDate": iso(sprint.end),
            "completeDate": iso(sprint.completed), "goal": sprint.goal or None,
            "boardId": sprint.board_id}  # fmt: skip


def filter_json(saved: Filter) -> dict[str, Any]:
    """Return a saved filter as JSON."""
    return {"id": saved.id, "name": saved.name, "jql": saved.jql, "owner": user_json(saved.owner),
            "description": saved.description or None, "favourite": saved.favourite,
            "sharedWith": list(saved.shared_with), "url": saved.url or None}  # fmt: skip


def column_json(column: FilterColumn) -> dict[str, Any]:
    """Return a filter's column as JSON."""
    return {"field": column.field, "label": column.label}


def field_json(info: FieldInfo) -> dict[str, Any]:
    """Return a field of the site as JSON."""
    return {"id": info.id, "name": info.name, "type": info.type or None, "custom": info.custom,
            "clauseNames": list(info.clauses)}  # fmt: skip


def dashboard_json(dashboard: Dashboard) -> dict[str, Any]:
    """Return a dashboard as JSON."""
    return {"id": dashboard.id, "name": dashboard.name, "owner": user_json(dashboard.owner),
            "description": dashboard.description or None, "favourite": dashboard.favourite,
            "popularity": dashboard.popularity, "url": dashboard.url or None}  # fmt: skip
