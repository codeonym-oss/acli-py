"""`CommentsView`: an issue's comments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import comment_json
from acli_py.domain.issue import Comment


@dataclass(frozen=True)
class CommentsView:
    """The comments on issue `key`."""

    key: str
    comments: tuple[Comment, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return the comments as JSON, bodies as Markdown."""
        return [comment_json(c) for c in self.comments]
