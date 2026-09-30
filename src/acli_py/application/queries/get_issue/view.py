"""`IssueView`: one issue as front ends show it, as a Rich panel, JSON or Markdown."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from rich.console import Group
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from acli_py.application.queries.shapes import (
    comment_json,
    iso,
    link_json,
    ref_json,
    status_json,
    user_json,
)
from acli_py.domain.issue import Issue, IssueRef, Link, Status, StatusCategory
from acli_py.domain.values import ago, text, when

if TYPE_CHECKING:
    from rich.console import RenderableType

STATUS_COLOURS = {
    StatusCategory.TO_DO: "blue",
    StatusCategory.IN_PROGRESS: "yellow",
    StatusCategory.DONE: "green",
}


@dataclass(frozen=True)
class IssueView:
    """An issue and where it lives on the site."""

    issue: Issue
    url: str

    # ── JSON ─────────────────────────────────────────────────────────────────

    def to_json(self) -> dict[str, Any]:
        """Return the issue as plain JSON data: stable names, Markdown text, ISO dates."""
        i = self.issue
        return {
            "key": i.key,
            "id": i.id,
            "url": self.url,
            "project": i.project,
            "summary": i.summary,
            "type": i.type.name if i.type else None,
            "status": status_json(i.status),
            "priority": i.priority or None,
            "resolution": i.resolution or None,
            "assignee": user_json(i.assignee),
            "reporter": user_json(i.reporter),
            "labels": list(i.labels),
            "components": list(i.components),
            "fixVersions": list(i.fix_versions),
            "parent": ref_json(i.parent),
            "due": iso(i.due),
            "created": iso(i.created),
            "updated": iso(i.updated),
            "description": i.description,
            "subtasks": [ref_json(s) for s in i.subtasks],
            "links": [link_json(link) for link in i.links],
            "comments": {
                "total": i.comment_count,
                "items": [comment_json(c) for c in i.comments],
            },
            "attachments": [
                {"id": a.id, "filename": a.filename, "size": a.size} for a in i.attachments
            ],
            "watchers": {"count": i.watchers, "watching": i.watching},
            "fields": {f.id: {"name": f.name, "value": f.value} for f in i.other},
        }

    # ── Markdown ─────────────────────────────────────────────────────────────

    def to_markdown(self, comments: int = 5, now: datetime | None = None) -> str:
        """Return the issue as Markdown, with its latest `comments` comments."""
        i = self.issue
        lines = [f"## {i.key} · {i.summary}", ""]
        updated = f"{when(i.updated)} ({ago(i.updated, now)} ago)" if i.updated else ""
        facts: list[tuple[str, Any]] = [
            ("Type", i.type.name if i.type else ""),
            ("Status", i.status.name if i.status else ""),
            ("Priority", i.priority),
            ("Assignee", i.assignee.name if i.assignee else "_unassigned_"),
            ("Reporter", i.reporter.name if i.reporter else ""),
            ("Labels", " ".join(f"`{label}`" for label in i.labels)),
            ("Components", ", ".join(i.components)),
            ("Fix versions", ", ".join(i.fix_versions)),
            ("Parent", _ref_text(i.parent)),
            ("Due", iso(i.due)),
            ("Resolution", i.resolution),
            ("Watchers", i.watchers or ""),
            ("Created", when(i.created)),
            ("Updated", updated),
            *((f.name, text(f.value)) for f in i.other),
        ]
        lines += [f"**{name}:** {value}  " for name, value in facts if value not in (None, "")]
        lines += ["", f"<{self.url}>", ""]
        lines += ["### Description", "", i.description or "_No description._", ""]
        if i.subtasks:
            lines += ["### Subtasks", ""]
            for sub in i.subtasks:
                status = f" [{sub.status.name}]" if sub.status else ""
                lines.append(f"- **{sub.key}**{status} {sub.summary}")
            lines.append("")
        if i.links:
            lines += ["### Links", ""]
            lines += [f"- {link.phrase} **{link.issue.key}** {link.issue.summary}"
                      for link in i.links]  # fmt: skip
            lines.append("")
        if i.comments:
            shown = i.comments[-comments:] if comments else ()
            more = i.comment_count - len(shown)
            lines += [f"### Comments ({i.comment_count})", ""]
            if more:
                lines += [f"_{more} older not shown._", ""]
            for comment in shown:
                author = comment.author.name if comment.author else "?"
                lines += [f"**{author}** · {when(comment.created)}", "", comment.body, "",
                          "---", ""]  # fmt: skip
        return "\n".join(lines)

    # ── Rich ─────────────────────────────────────────────────────────────────

    def to_rich(self, comments: int = 3) -> Group:
        """Return the issue as a Rich panel of facts, then its text, subtasks, links, comments."""
        i = self.issue
        facts: list[tuple[str, str]] = [
            ("Type", escape(i.type.name) if i.type else ""),
            ("Status", status_markup(i.status)),
            ("Priority", escape(i.priority)),
            ("Assignee", escape(i.assignee.name) if i.assignee else "[dim]unassigned[/]"),
            ("Reporter", escape(i.reporter.name) if i.reporter else ""),
            ("Parent", escape(_ref_text(i.parent))),
            ("Labels", escape(", ".join(i.labels))),
            ("Components", escape(", ".join(i.components))),
            ("Fix versions", escape(", ".join(i.fix_versions))),
            ("Resolution", escape(i.resolution)),
            ("Due", iso(i.due) or ""),
            ("Created", when(i.created)),
            ("Updated", when(i.updated)),
            *((escape(f.name), escape(text(f.value))) for f in i.other),
            ("URL", f"[dim]{escape(self.url)}[/]"),
        ]
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold cyan", justify="right", no_wrap=True)
        grid.add_column(overflow="fold")
        for label, value in facts:
            if value:
                grid.add_row(label, value)
        parts: list[RenderableType] = [
            Panel(grid, title=f"[bold]{escape(i.key)}  {escape(i.summary)}[/]",
                  title_align="left", border_style="blue", expand=False)
        ]  # fmt: skip
        if i.description:
            parts.append(Panel(Markdown(i.description), title="Description", title_align="left"))
        if i.subtasks:
            parts.append(Rule("Subtasks", align="left", style="dim"))
            parts += [f"  {_ref_markup(sub)}" for sub in i.subtasks]
        if i.links:
            parts.append(Rule("Links", align="left", style="dim"))
            parts += [f"  {_link_markup(link)}" for link in i.links]
        if i.attachments:
            parts.append(Rule("Attachments", align="left", style="dim"))
            parts += [f"  [dim]{escape(a.id)}[/]  {escape(a.filename)}  [dim]{size(a.size)}[/]"
                      for a in i.attachments]  # fmt: skip
        if comments and i.comments:
            parts.append(Rule(f"Comments ({i.comment_count})", align="left", style="dim"))
            for comment in i.comments[-comments:]:
                author = escape(comment.author.name) if comment.author else "?"
                parts.append(f"[bold]{author}[/] [dim]{when(comment.created)} · id {comment.id}[/]")
                parts.append(Markdown(comment.body or "_(empty)_"))
        return Group(*parts)


def status_markup(status: Status | None) -> str:
    """Return a status name coloured by its category, as Rich markup."""
    if status is None:
        return ""
    return f"[{STATUS_COLOURS.get(status.category, 'white')}]{escape(status.name)}[/]"


def size(count: float) -> str:
    """Return a byte count for people: 512 B, 1.5 KB, 3.2 MB."""
    for unit in ("B", "KB", "MB", "GB"):
        if count < 1024 or unit == "GB":
            return f"{count:.0f} {unit}" if unit == "B" else f"{count:.1f} {unit}"
        count /= 1024
    return str(count)  # pragma: no cover - the loop always returns


def _ref_text(ref: IssueRef | None) -> str:
    return f"{ref.key} {ref.summary}".strip() if ref else ""


def _ref_markup(ref: IssueRef) -> str:
    return f"{escape(ref.key)}  {status_markup(ref.status)}  {escape(ref.summary)}"


def _link_markup(link: Link) -> str:
    other = link.issue
    return (
        f"[dim]{escape(link.phrase)}[/] {escape(other.key)} {status_markup(other.status)} "
        f"{escape(other.summary)} [dim](link {escape(link.id)})[/]"
    )
