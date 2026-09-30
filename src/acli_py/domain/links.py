"""Links between issues, read as sentences: 'DEMO-1 blocks DEMO-2'.

Every link type has two phrases: the outward one ('blocks') reads from the outward issue to
the inward one, and the inward one ('is blocked by') reads back. `LinkDirection` is the rule
that turns what the user wrote, with either phrase or the type's name, into the one `IssueLink`
Jira stores:

    DEMO-1 blocks DEMO-2         ->  outward DEMO-1, inward DEMO-2
    DEMO-2 is blocked by DEMO-1  ->  outward DEMO-1, inward DEMO-2 (the same link)
    DEMO-1 Blocks DEMO-2         ->  a type's name reads as its outward phrase
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable


class UnknownLinkTypeError(ValueError):
    """No link type has that name or phrase; the message lists the ones there are."""


@dataclass(frozen=True)
class LinkType:
    """A kind of link: its name ('Blocks') and its two phrases."""

    name: str
    outward: str
    inward: str
    id: str = ""

    @classmethod
    def from_jira(cls, data: Any) -> LinkType:
        """Return the link type in Jira's JSON."""
        data = data if isinstance(data, dict) else {}
        name = str(data.get("name") or "")
        return cls(
            name,
            str(data.get("outward") or name),
            str(data.get("inward") or name),
            str(data.get("id") or ""),
        )

    def __str__(self) -> str:
        """Return 'Blocks (blocks / is blocked by)'."""
        return f"{self.name} ({self.outward} / {self.inward})"


@dataclass(frozen=True)
class IssueLink:
    """One link as Jira stores it: '`outward` <type's outward phrase> `inward`'."""

    type: LinkType
    outward: str
    inward: str

    def __str__(self) -> str:
        """Return the link as a sentence: 'DEMO-1 blocks DEMO-2'."""
        return f"{self.outward} {self.type.outward} {self.inward}"

    def to_jira(self) -> dict[str, Any]:
        """Return the body of `POST /issueLink` for this link."""
        return {
            "type": {"name": self.type.name},
            "outwardIssue": {"key": self.outward},
            "inwardIssue": {"key": self.inward},
        }

    @classmethod
    def from_jira(cls, data: Any) -> IssueLink:
        """Return the link in `GET /issueLink/{id}`'s JSON."""
        data = data if isinstance(data, dict) else {}
        outward, inward = data.get("outwardIssue") or {}, data.get("inwardIssue") or {}
        return cls(
            LinkType.from_jira(data.get("type")),
            str(outward.get("key") or ""),
            str(inward.get("key") or ""),
        )


class LinkDirection:
    """The rule for reading 'SOURCE <type or phrase> TARGET' as the link Jira stores."""

    def __init__(self, types: Iterable[LinkType]) -> None:
        self.types = tuple(types)

    def read(self, wanted: str) -> tuple[LinkType, bool]:
        """Return the type `wanted` names, and whether it reads outward.

        A name or outward phrase reads outward; an inward phrase ('is blocked by') doesn't.
        Raises `UnknownLinkTypeError` when no type matches.
        """
        lowered = wanted.strip().lower()
        for kind in self.types:
            if lowered in (kind.name.lower(), kind.outward.lower()):
                return kind, True
        for kind in self.types:
            if lowered == kind.inward.lower():
                return kind, False
        known = "; ".join(str(t) for t in self.types)
        raise UnknownLinkTypeError(f"no link type {wanted!r}. Available: {known}")

    def link(self, source: str, wanted: str, target: str) -> IssueLink:
        """Return the link that 'source <wanted> target' says."""
        kind, outward = self.read(wanted)
        source, target = source.strip().upper(), target.strip().upper()
        if not outward:
            source, target = target, source
        return IssueLink(kind, source, target)

    def named(self, name: str) -> LinkType | None:
        """Return the type called `name` (any case), or None."""
        return next((t for t in self.types if t.name.lower() == name.lower()), None)
