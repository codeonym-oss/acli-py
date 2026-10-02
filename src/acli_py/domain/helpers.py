"""Rules for the everyday helpers: which day a standup looks back to, and git names for issues."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from acli_py.domain.issue import Issue

SLUG_WORDS = 6
SLUG_LENGTH = 50
# Issue types whose work is a fix, in branch names and commit messages; the rest are features.
FIX_TYPES = ("bug", "defect", "incident", "problem")


def last_working_day(today: date) -> date:
    """Return the working day before `today`: Friday for a Monday or a weekend, else yesterday."""
    back = {0: 3, 6: 2}.get(today.weekday(), 1)  # Monday and Sunday go back to Friday
    return today - timedelta(days=back)


def slug(text: str, words: int = SLUG_WORDS, length: int = SLUG_LENGTH) -> str:
    """Return text as a lowercase, hyphenated slug of a few words: 'login-fails-on-safari'."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    parts = re.findall(r"[a-z0-9]+", ascii_text.lower())[:words]
    return "-".join(parts)[:length].strip("-")


def kind_of(issue: Issue) -> str:
    """Return 'fix' for an issue whose type is a defect, else 'feat'."""
    name = issue.type.name.lower() if issue.type else ""
    return "fix" if name in FIX_TYPES else "feat"


def branch_name(issue: Issue, prefix: str | None = None) -> str:
    """Return a branch for the issue: 'fix/DEMO-1-login-fails-on-safari'.

    `prefix` replaces the type ('fix', 'feat'); an empty one leaves it out.
    """
    lead = kind_of(issue) if prefix is None else prefix.strip("/")
    name = "-".join(p for p in (issue.key, slug(issue.summary)) if p)
    return f"{lead}/{name}" if lead else name


def commit_message(issue: Issue) -> str:
    """Return a Conventional Commit subject for the issue: 'fix: login fails on Safari (DEMO-1)'."""
    summary = issue.summary.strip().rstrip(".")
    if summary[:1].isupper() and not summary[1:2].isupper():
        summary = summary[0].lower() + summary[1:]
    return f"{kind_of(issue)}: {summary} ({issue.key})"
