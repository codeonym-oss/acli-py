from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Command, command

from acli_py.application.changes import Change, Changed


@command
@dataclass(frozen=True)
class LinkIssues(Command[Changed]):
    """Link `source` and `target` as '`source` `kind` `target`'.

    `kind` is a link type's name or either of its phrases ('blocks', 'is blocked by').
    `comment` (Markdown) is added to the link's outward issue. Adding one link doesn't ask
    first; adding several asks once.
    """

    source: str
    kind: str
    target: str
    comment: str = ""

    @property
    def item(self) -> str:
        """Return the link as written: 'DEMO-1 blocks DEMO-2'."""
        return f"{self.source.strip().upper()} {self.kind.strip()} {self.target.strip().upper()}"

    def change(self) -> Change:
        """Return what this command changes: 'Add link DEMO-1 blocks DEMO-2'."""
        return Change("Add", (self.item,), subject=f"link {self.item}", noun="link", adds=True)
