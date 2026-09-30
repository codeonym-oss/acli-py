from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.comment_on_issue.command import CommentOnIssue
from acli_py.application.ports import Comments
from acli_py.domain import adf


@command_handler
def comment_on_issue(request: CommentOnIssue, comments: Comments) -> Changed:
    """Add the comment, or replace the latest one; `Changed` names the comment."""
    key = request.key.strip().upper()
    body = adf.to_adf(request.body)
    if request.replacing:
        latest = next(
            (
                c
                for c in comments.comments(key, newest_first=True)
                if c.author and c.author.account_id == request.replacing
            ),
            None,
        )
        if latest is not None:
            comments.update(key, latest.id, body, request.audience, notify=True)
            return Changed(
                key,
                before={"comment": latest.id, "body": latest.body},
                after={"comment": latest.id, "body": adf.to_text(body).strip()},
            )
    return Changed(key, after={"comment": comments.add(key, body, request.audience)})
