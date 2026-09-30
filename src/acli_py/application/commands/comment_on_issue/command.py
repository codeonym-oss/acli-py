from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed
from acli_py.domain.issue import Audience


@command
@dataclass(frozen=True)
class CommentOnIssue(Command[Changed]):
    """Comment on an issue: `body` is Markdown, or an ADF JSON document.

    `audience` keeps the comment to a project role or a group. `replacing` is an account id:
    that person's latest comment on the issue is replaced instead, when they have one.
    Commenting on one issue doesn't ask first; on several, it asks once.
    """

    key: str
    body: str
    audience: Audience | None = None
    replacing: str = ""

    def change(self) -> Change:
        """Return what this command changes: 'Comment on DEMO-1'."""
        key = self.key.strip().upper()
        if self.replacing:
            return Change("Replace the latest comment on", (key,))
        return Change("Comment on", (key,), adds=True)
