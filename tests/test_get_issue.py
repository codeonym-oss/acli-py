"""The `get_issue` use case, layer by layer: domain parsing, the handler, the view."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from typing import Any

import pytest
from mediary import Mediator
from rich.console import Console

from acli_py.application.ports import IssueReader
from acli_py.application.queries import get_issue as get_issue_package
from acli_py.application.queries.get_issue.query import GetIssue
from acli_py.application.queries.get_issue.view import IssueView, size
from acli_py.bootstrap import build_bus
from acli_py.domain.adf import to_adf
from acli_py.domain.issue import Direction, Issue, StatusCategory, User
from acli_py.domain.values import moment, text, when
from acli_py.infrastructure.jira.client import JiraClient, NotFoundError
from acli_py.infrastructure.jira.site import Site
from tests import fake_jira

ISSUE = {
    "id": "10001",
    "key": "DEMO-9",
    "names": {"customfield_10016": "Story point estimate"},
    "fields": {
        "summary": "Pay by card",
        "project": {"key": "DEMO"},
        "issuetype": {"name": "Story", "subtask": False},
        "status": {"name": "In Review", "statusCategory": {"key": "indeterminate"}},
        "priority": {"name": "High"},
        "assignee": {"accountId": "a1", "displayName": "Alice", "emailAddress": "a@x.io"},
        "reporter": {"accountId": "b2", "displayName": "Bob"},
        "labels": ["pay", "web"],
        "components": [{"name": "API"}],
        "fixVersions": [{"name": "2.4"}],
        "parent": {"key": "DEMO-1", "fields": {"summary": "Checkout"}},
        "duedate": "2026-10-01",
        "created": "2026-09-22T10:00:00.000+0200",
        "updated": "2026-09-23T11:30:00.000+0200",
        "resolution": None,
        "description": to_adf("Use **Stripe**."),
        "subtasks": [
            {"key": "DEMO-10", "fields": {"summary": "Sub", "status": {"name": "Done",
                                                                      "statusCategory": {"key": "done"}}}}
        ],
        "issuelinks": [
            {"id": "7", "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
             "inwardIssue": {"key": "DEMO-2", "fields": {"summary": "Keys"}}},
            {"id": "8", "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
             "outwardIssue": {"key": "DEMO-3", "fields": {"summary": "Ship"}}},
            {"id": "9", "type": {"name": "Broken"}},
        ],
        "comment": {
            "total": 9,
            "comments": [{"id": str(n), "author": {"displayName": "Bob"}, "body": to_adf(f"c{n}"),
                          "created": "2026-09-24T09:15:00.000+0200"} for n in range(7)],
        },
        "attachment": [{"id": "30", "filename": "trace.log", "size": 2048}],
        "watches": {"watchCount": 2, "isWatching": True},
        "customfield_10016": 5.0,
        "customfield_10020": None,
    },
}  # fmt: skip


# ── domain ───────────────────────────────────────────────────────────────────


def test_issue_reads_jira_json():
    issue = Issue.from_jira(ISSUE)
    assert (issue.key, issue.id, issue.project, issue.summary) == (
        "DEMO-9",
        "10001",
        "DEMO",
        "Pay by card",
    )
    assert issue.type is not None
    assert issue.type.name == "Story"
    assert issue.status is not None
    assert issue.status.category is StatusCategory.IN_PROGRESS
    assert issue.assignee == User("a1", "Alice", "a@x.io")
    assert issue.labels == ("pay", "web")
    assert (issue.components, issue.fix_versions) == (("API",), ("2.4",))
    assert issue.parent is not None
    assert issue.parent.key == "DEMO-1"
    assert issue.due == date(2026, 10, 1)
    assert issue.created is not None
    assert issue.created.utcoffset() is not None
    assert issue.description == "Use **Stripe**."
    assert issue.subtasks[0].status is not None
    assert issue.subtasks[0].status.category is StatusCategory.DONE
    assert [(link.direction, link.phrase, link.issue.key) for link in issue.links] == [
        (Direction.INWARD, "is blocked by", "DEMO-2"),
        (Direction.OUTWARD, "blocks", "DEMO-3"),
    ]
    assert (len(issue.comments), issue.comment_count, issue.comments[0].body) == (7, 9, "c0")
    assert issue.attachments[0].size == 2048
    assert (issue.watchers, issue.watching) == (2, True)
    assert [(f.id, f.name, f.value) for f in issue.other] == [
        ("customfield_10016", "Story point estimate", 5.0)
    ]


def test_issue_tolerates_what_jira_leaves_out():
    issue = Issue.from_jira({"key": "DEMO-1", "fields": {
        "status": {"name": "Odd", "statusCategory": {"key": "sideways"}},
        "assignee": {}, "labels": None, "duedate": "soon", "created": "yesterday",
    }})  # fmt: skip
    assert issue.status is not None
    assert issue.status.category is StatusCategory.UNKNOWN
    assert (issue.assignee, issue.type, issue.parent, issue.due, issue.created) == (None,) * 5
    assert (issue.labels, issue.comments, issue.comment_count, issue.other) == ((), (), 0, ())
    assert Issue.from_jira({"key": "X-1"}).summary == ""


def test_values_read_times_and_any_field():
    assert when("2026-09-22T10:00:00.000+0200") == "2026-09-22 10:00"
    assert when("2026-09-22T10:00:00") == "2026-09-22 10:00"
    assert when("not a time") == "not a time"
    assert moment("2026-09-22T10:00:00+0000") == datetime(2026, 9, 22, 10, tzinfo=UTC)
    assert text([{"value": "Blue", "child": {"value": "Navy"}}, True, 2.50, None]) == (
        "Blue > Navy, yes, 2.5"
    )
    assert text({"odd": 1}) == '{"odd": 1}'
    assert text(to_adf("Two\n\nlines")) == "Two lines"


# ── handler ──────────────────────────────────────────────────────────────────


class StubIssues:
    """An `IssueReader` answering from memory, recording what it was asked."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, tuple[str, ...]]] = []

    def get_issue(self, key: str, fields: tuple[str, ...] = ()) -> Issue:
        self.asked.append((key, fields))
        return Issue.from_jira(ISSUE)

    def browse_url(self, key: str) -> str:
        return f"https://x.test/browse/{key}"


def test_handler_reads_through_the_port():
    stub = StubIssues()

    class Resolver:
        def resolve(self, cls: Any, /) -> Any:
            assert cls is IssueReader
            return stub

    mediator = Mediator(resolver=Resolver())
    mediator.scan(get_issue_package)
    view = asyncio.run(mediator.send(GetIssue(" demo-9 ", ("customfield_10016",))))
    assert stub.asked == [("DEMO-9", ("customfield_10016",))]
    assert view.url == "https://x.test/browse/DEMO-9"
    assert view.issue.key == "DEMO-9"


def test_handler_against_the_fake_site(site, fake):
    _, url = fake
    client = JiraClient(url, fake_jira.EMAIL, fake_jira.TOKEN)
    bus = build_bus(Site(client, url))
    view = asyncio.run(bus.send(GetIssue("demo-1", ("customfield_10016",))))
    assert view.issue.summary == "Login fails on Safari"
    assert view.issue.links[0].issue.key == "DEMO-3"
    assert view.issue.comments[-1].body == "Seen on **Safari 18** too."
    assert [(f.name, f.value) for f in view.issue.other] == [("Story point estimate", 3)]
    assert view.url == f"{url}/browse/DEMO-1"
    everything = asyncio.run(bus.send(GetIssue("DEMO-2", ("*all",))))
    assert everything.issue.assignee is not None
    assert everything.issue.assignee.name == "Bob Jensen"
    with pytest.raises(NotFoundError):
        asyncio.run(bus.send(GetIssue("NOPE-1")))
    assert site.writes() == []


# ── view ─────────────────────────────────────────────────────────────────────

VIEW = IssueView(Issue.from_jira(ISSUE), "https://x.test/browse/DEMO-9")


def test_view_as_markdown():
    text = VIEW.to_markdown(now=datetime(2026, 9, 23, 12, 30, tzinfo=UTC))
    assert text.startswith("## DEMO-9 · Pay by card")
    for line in ("**Status:** In Review  ", "**Labels:** `pay` `web`  ",
                 "**Parent:** DEMO-1 Checkout  ", "**Watchers:** 2  ",
                 "**Updated:** 2026-09-23 11:30 (3h ago)  ",
                 "**Story point estimate:** 5  ", "<https://x.test/browse/DEMO-9>",
                 "- **DEMO-10** [Done] Sub", "- is blocked by **DEMO-2** Keys",
                 "### Comments (9)", "_4 older not shown._"):  # fmt: skip
        assert line in text, line
    bare = IssueView(Issue("DEMO-5"), "u").to_markdown()
    assert "_No description._" in bare
    assert "**Assignee:** _unassigned_" in bare


def test_view_as_json():
    data = json.loads(json.dumps(VIEW.to_json()))
    assert data["status"] == {"name": "In Review", "category": "indeterminate"}
    assert data["assignee"] == {"accountId": "a1", "name": "Alice", "email": "a@x.io"}
    assert data["reporter"]["email"] is None
    assert data["due"] == "2026-10-01"
    assert data["created"] == "2026-09-22T10:00:00+02:00"
    assert data["links"][1] == {
        "id": "8", "type": "Blocks", "direction": "outward", "phrase": "blocks",
        "issue": {"key": "DEMO-3", "summary": "Ship", "status": None},
    }  # fmt: skip
    assert data["comments"]["total"] == 9
    assert data["fields"] == {"customfield_10016": {"name": "Story point estimate", "value": 5.0}}
    assert data["watchers"] == {"count": 2, "watching": True}


def test_view_as_rich():
    console = Console(width=120, record=True, color_system=None)
    console.print(VIEW.to_rich(comments=2))
    out = console.export_text()
    for part in ("DEMO-9  Pay by card", "In Review", "Story point estimate", "Stripe",
                 "DEMO-10", "is blocked by DEMO-2", "trace.log", "2.0 KB",
                 "Comments (9)", "c6"):  # fmt: skip
        assert part in out, part
    assert "c4" not in out
    console = Console(width=120, record=True, color_system=None)
    console.print(IssueView(Issue("DEMO-5"), "u").to_rich())
    assert "unassigned" in console.export_text()


def test_sizes_read_well():
    assert [size(n) for n in (512, 1536, 3 * 1024**2, 5 * 1024**4)] == [
        "512 B", "1.5 KB", "3.0 MB", "5120.0 GB",
    ]  # fmt: skip
