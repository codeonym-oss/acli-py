"""`SprintReportView`: a sprint's issues counted by status and by assignee."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import sprint_json
from acli_py.domain.agile import Sprint
from acli_py.domain.issue import Issue, StatusCategory

# The categories, left to right on a board, as a report names them.
CATEGORIES = {
    StatusCategory.TO_DO: "To Do",
    StatusCategory.IN_PROGRESS: "In Progress",
    StatusCategory.DONE: "Done",
}
NOBODY = "Unassigned"


@dataclass(frozen=True)
class SprintReportView:
    """A sprint and its issues, with the counts a report shows."""

    sprint: Sprint
    issues: tuple[Issue, ...]

    def category(self, issue: Issue) -> StatusCategory:
        """Return where the issue is: to do, in progress or done."""
        found = issue.status.category if issue.status else StatusCategory.UNKNOWN
        return found if found in CATEGORIES else StatusCategory.TO_DO

    @property
    def done(self) -> float:
        """Return the share of issues done, 0 to 1 (0 for an empty sprint)."""
        if not self.issues:
            return 0.0
        return sum(self.category(i) is StatusCategory.DONE for i in self.issues) / len(self.issues)

    def by_status(self) -> list[tuple[str, str, int]]:
        """Return (category, status, count) per status, in board order."""
        counts = Counter(
            (self.category(i), i.status.name if i.status else "?") for i in self.issues
        )
        order = list(CATEGORIES)
        ordered = sorted(counts.items(), key=lambda kv: (order.index(kv[0][0]), kv[0][1]))
        return [(CATEGORIES[c], status, n) for (c, status), n in ordered]

    def by_assignee(self) -> list[tuple[str, dict[str, int]]]:
        """Return each assignee with their issues counted per category, busiest first."""
        people: dict[str, Counter[StatusCategory]] = {}
        for issue in self.issues:
            name = issue.assignee.name if issue.assignee else NOBODY
            people.setdefault(name, Counter())[self.category(issue)] += 1
        rows = [
            (name, {label: counts[c] for c, label in CATEGORIES.items()})
            for name, counts in people.items()
        ]
        return sorted(rows, key=lambda row: (-sum(row[1].values()), row[0]))

    def to_json(self) -> dict[str, Any]:
        """Return the report as JSON."""
        return {
            "sprint": sprint_json(self.sprint),
            "issues": len(self.issues),
            "done": round(self.done, 3),
            "byStatus": [{"category": c, "status": s, "issues": n} for c, s, n in self.by_status()],
            "byAssignee": [
                {"assignee": name, "counts": counts} for name, counts in self.by_assignee()
            ],
        }
