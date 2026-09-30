"""The JSON shapes views share: users, statuses, issue references, comments, links.

Keys are camelCase, as in Jira's own JSON; dates are ISO strings; missing values are null.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from acli_py.domain.issue import Attachment, Comment, IssueRef, Link, Status, User, Worklog


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
