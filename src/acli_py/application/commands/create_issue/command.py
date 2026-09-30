from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed, PreviewRow
from acli_py.domain import adf
from acli_py.domain.values import text


@command
@dataclass(frozen=True)
class CreateIssue(Command[Changed]):
    """Create an issue from `fields` and `update`, as Jira takes them.

    `ref` names the issue until it has a key: its row in a file ('#3'), in questions and
    reports. Creating one issue doesn't ask first; creating several asks once.
    """

    fields: Mapping[str, Any]
    update: Mapping[str, Any] = field(default_factory=dict)
    ref: str = "#1"

    @classmethod
    def of(
        cls,
        project: str,
        issue_type: str,
        summary: str,
        description: str = "",
        *,
        assignee: str | None = None,
        labels: Sequence[str] = (),
    ) -> CreateIssue:
        """Return the command for an issue with a few plain values (Markdown description)."""
        fields: dict[str, Any] = {
            "project": {"key": project.strip().upper()},
            "issuetype": {"name": issue_type},
            "summary": summary.strip(),
        }
        if description.strip():
            fields["description"] = adf.to_adf(description)
        if assignee:
            fields["assignee"] = {"accountId": assignee}
        if labels:
            fields["labels"] = list(labels)
        return cls(fields)

    @property
    def key(self) -> str:
        """Return what names the issue before it exists (the bulk engine reports on it)."""
        return self.ref

    @property
    def summary(self) -> str:
        """Return the new issue's summary."""
        return str(self.fields.get("summary") or "")

    @property
    def where(self) -> str:
        """Return the new issue's type and project: 'Bug in DEMO' ('issue' when unknown)."""
        kind = text(self.fields.get("issuetype")) or "issue"
        project = text(self.fields.get("project"))
        return f"{kind} in {project}" if project else kind

    def change(self) -> Change:
        """Return what this command changes: 'Create a Bug in DEMO: "Login fails"'."""
        subject = f"a {self.where}" + (f': "{self.summary}"' if self.summary else "")
        return Change("Create", (self.ref,), subject=subject, adds=True)

    def preview_row(self) -> PreviewRow:
        """Return the new issue as a preview row: its summary, and what it will be."""
        return PreviewRow(self.ref, self.summary, "", self.where)
