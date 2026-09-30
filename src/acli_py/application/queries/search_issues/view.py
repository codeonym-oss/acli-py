"""`IssuesView`: a list of issues, in the columns asked for."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from acli_py.application.queries.issue_columns import IssueColumn, Template
from acli_py.application.queries.issue_columns import columns as pick_columns

if TYPE_CHECKING:
    from collections.abc import Iterable

    from acli_py.domain.issue import Issue


@dataclass(frozen=True)
class IssuesView:
    """Issues found by `jql`, shown in `columns`; `next_token` goes on to more, when any."""

    jql: str
    issues: tuple[Issue, ...]
    columns: tuple[IssueColumn, ...] = pick_columns()
    next_token: str | None = None

    @classmethod
    def of(cls, issues: Iterable[Issue], names: Iterable[str] = (), jql: str = "") -> IssuesView:
        """Return a view of issues found some other way (a board, a sprint)."""
        return cls(jql, tuple(issues), pick_columns(names))

    def to_json(self) -> list[dict[str, Any]]:
        """Return each issue as JSON, with one member per column."""
        return [{c.name: c.json(i) for c in self.columns} for i in self.issues]

    def to_text(self) -> list[dict[str, str]]:
        """Return each issue as short text per column, for tables and CSV."""
        return [{c.name: c.text(i) for c in self.columns} for i in self.issues]

    def lines(self, template: Template) -> list[str]:
        """Return one line per issue: `template` filled in."""
        return [template.render(i) for i in self.issues]
