"""Reading issues as queries: compiling searches, the views' shapes, history, and the CLI."""

from __future__ import annotations

import csv
import json

import pytest

from acli_py.application.queries.compile_search.handler import compile_search
from acli_py.application.queries.compile_search.query import (
    ME,
    NOBODY,
    CompileSearch,
    NothingToSearchError,
)
from acli_py.application.queries.get_history.handler import get_history
from acli_py.application.queries.get_history.query import GetHistory
from acli_py.application.queries.issue_columns import Template, column, columns, jira_fields
from acli_py.application.queries.search_issues.handler import search_issues
from acli_py.application.queries.search_issues.query import SearchIssues
from acli_py.application.queries.search_issues.view import IssuesView
from acli_py.domain.history import FieldChange, HistoryEntry
from acli_py.domain.issue import Issue, User
from acli_py.domain.jql import StaticCatalog, Value
from tests import fake_jira
from tests.conftest import run_cli

BUG = Issue.from_jira({
    "key": "DEMO-1",
    "fields": {"summary": "Login fails", "issuetype": {"name": "Bug"},
               "status": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}},
               "assignee": {"accountId": "a1", "displayName": "Alice"}, "labels": ["web", "ui"],
               "duedate": "2026-10-01", "customfield_10016": 3.0},
})  # fmt: skip
BOB = User("b2", "Bob")


def ok(*args: str, input: str | None = None) -> str:
    result, out = run_cli(*args, input=input)
    assert result.exit_code == 0, out
    return out


# ── compiling a search ───────────────────────────────────────────────────────


class Filters:
    """An `IssueSearch` that only knows saved filters."""

    def filter_jql(self, filter_id: str) -> str:
        return {"7": "project = DEMO ORDER BY rank"}[filter_id]


def compiled(**kwargs) -> str:
    catalog = StaticCatalog(field_values={"status": [Value("In Progress")]})
    return compile_search(CompileSearch(**kwargs), Filters(), catalog).jql  # type: ignore[arg-type]


def test_every_option_is_anded_and_the_order_kept():
    assert compiled(
        text="labels = web ORDER BY created",
        statuses=("To Do", "In Progress"),
        types=("Bug",),
        labels=('a"b',),
        words="safari",
        open_only=True,
        assignee=NOBODY,
    ) == (
        '(labels = web) AND assignee is EMPTY AND status in ("To Do", "In Progress") '
        'AND issuetype = "Bug" AND labels = "a\\"b" AND text ~ "safari" '
        "AND statusCategory != Done ORDER BY created"
    )
    assert compiled(project="x", order="-created") == 'project = "X" ORDER BY created DESC'
    assert compiled(assignee="b2", project="X").startswith('project = "X" AND assignee = "b2"')
    assert "assignee = currentUser()" in compiled(assignee=ME)


def test_smart_queries_compile_with_the_sites_spelling():
    jql = compiled(text="s:progress")
    assert 'status = "In Progress"' in jql
    assert compiled(text="s:progress", raw=True) == "(s:progress) ORDER BY updated DESC"


def test_a_saved_filter_joins_the_query_and_brings_its_order():
    assert compiled(saved_filter="7", text="labels = web") == (
        "(project = DEMO) AND (labels = web) ORDER BY rank"
    )


def test_with_nothing_to_search_the_default_project_is_searched():
    assert compiled(default_project="ops") == 'project = "OPS" ORDER BY updated DESC'
    with pytest.raises(NothingToSearchError):
        compiled()


# ── columns and templates ────────────────────────────────────────────────────


def test_columns_read_names_in_any_case_and_jiras_ids():
    assert [c.name for c in columns(["Status", "issuetype", "key", "duedate"])] == [
        "key", "status", "type", "due",
    ]  # fmt: skip
    assert [c.name for c in columns()] == ["key", "type", "status", "priority", "assignee",
                                           "summary"]  # fmt: skip
    assert jira_fields(columns(["due", "customfield_10016"])) == ("duedate", "customfield_10016")
    points = column("customfield_10016")
    assert (points.text(BUG), points.json(BUG)) == ("3", 3.0)


def test_a_template_fills_in_columns_and_specs():
    template = Template(r"{key:<8}|{Status}\t{labels}|{customfield_10016}")
    assert template.names == ("key", "status", "labels", "customfield_10016")
    assert template.render(BUG) == "DEMO-1  |In Progress\tweb, ui|3"
    assert Template("{{literal}} {key}").render(BUG) == "{literal} DEMO-1"


@pytest.mark.parametrize("bad", ["{}", "{0}", "{key", "{fields.x}"])
def test_a_template_must_name_its_fields(bad):
    with pytest.raises(ValueError, match="format"):
        Template(bad)


def test_the_view_shows_the_columns_asked_for():
    view = IssuesView.of([BUG], ["status", "assignee", "due"])
    assert view.to_json() == [{
        "key": "DEMO-1", "status": {"name": "In Progress", "category": "indeterminate"},
        "assignee": {"accountId": "a1", "name": "Alice", "email": None}, "due": "2026-10-01",
    }]  # fmt: skip
    assert view.to_text() == [
        {"key": "DEMO-1", "status": "In Progress", "assignee": "Alice", "due": "2026-10-01"}
    ]


class Found:
    """An `IssueSearch` that returns BUG, and remembers what it was asked."""

    def __init__(self) -> None:
        self.asked: list[tuple] = []

    def search(self, jql, fields, *, limit, token=None):
        self.asked.append((jql, fields, limit, token))
        return [BUG], "next"


def test_the_search_fetches_what_its_columns_need():
    found = Found()
    view = search_issues(SearchIssues("project = DEMO", 10, ("summary", "due")), found)  # type: ignore[arg-type]
    assert found.asked == [("project = DEMO", ("summary", "duedate"), 10, None)]
    assert (view.issues, view.next_token) == ((BUG,), "next")


# ── history ──────────────────────────────────────────────────────────────────


class Changelog:
    """An `IssueReader` with a two-entry changelog."""

    def history(self, key: str) -> list[HistoryEntry]:
        assert key == "DEMO-1"
        return [
            HistoryEntry("1", BOB, None, (FieldChange("status", "To Do", "In Progress"),
                                          FieldChange("labels", "", "web"))),
            HistoryEntry("2", None, None, (FieldChange("Status", "In Progress", "Done",
                                                       "status"),)),
        ]  # fmt: skip


def test_history_is_one_row_per_field_changed():
    view = get_history(GetHistory("demo-1"), Changelog())  # type: ignore[arg-type]
    assert [str(r.change) for r in view.rows] == [
        "status: To Do → In Progress", "labels: ∅ → web", "Status: In Progress → Done",
    ]  # fmt: skip
    only = get_history(GetHistory("DEMO-1", "STATUS", newest_first=True, limit=1), Changelog())  # type: ignore[arg-type]
    assert only.to_json() == [{"id": "2", "at": None, "author": None, "field": "Status",
                               "fieldId": "status", "from": "In Progress", "to": "Done"}]  # fmt: skip


def test_changelog_entries_read_from_jira():
    entry = HistoryEntry.from_jira({
        "id": "9", "author": {"accountId": "b2", "displayName": "Bob"},
        "created": "2026-09-22T11:00:00.000+0200",
        "items": [{"field": "status", "fieldId": "status", "fromString": "To Do",
                   "toString": "Done"}],
    })  # fmt: skip
    assert entry.author == BOB
    assert entry.at is not None
    assert entry.changes == (FieldChange("status", "To Do", "Done", "status"),)


# ── the CLI ──────────────────────────────────────────────────────────────────


def test_search_formats_lines_for_pipes(site):
    out = ok("issue", "search", "-p", "DEMO", "--format", r"{key}\t{status}")
    assert out.splitlines() == ["DEMO-1\tTo Do", "DEMO-2\tTo Do", "DEMO-3\tIn Progress"]
    result, out = run_cli("issue", "search", "-p", "DEMO", "--format", "{key}", "--json")
    assert result.exit_code == 1
    assert "choose one of --format" in out


def test_search_fields_shape_json_and_csv(site):
    data = json.loads(ok("issue", "search", "-p", "DEMO", "--fields", "status,customfield_10016",
                         "--json"))  # fmt: skip
    assert data[0] == {"key": "DEMO-1", "status": {"name": "To Do", "category": "new"},
                       "customfield_10016": 3}  # fmt: skip
    rows = list(csv.reader(ok("issue", "search", "-p", "DEMO", "--fields", "labels",
                              "--csv").splitlines()))  # fmt: skip
    assert rows[:2] == [["Key", "Labels"], ["DEMO-1", "web"]]
    assert ok("issue", "search", "-p", "DEMO", "--output", "keys").split() == [
        "DEMO-1", "DEMO-2", "DEMO-3",
    ]  # fmt: skip


def test_count_takes_the_search_options(site):
    assert ok("issue", "count", "-p", "DEMO").strip() == "3"
    data = json.loads(ok("issue", "count", "-p", "DEMO", "--assignee", "@me", "--json"))
    assert data == {"jql": 'project = "DEMO" AND assignee = currentUser() ORDER BY updated DESC',
                    "count": 1}  # fmt: skip


def test_history_shows_who_changed_what(site):
    ok("issue", "transition", "DEMO-2", "--to", "Done", "-y")
    out = ok("issue", "history", "DEMO-1")
    assert "Bob Jensen" in out
    assert "In Progress" in out
    data = json.loads(ok("issue", "history", "DEMO-2", "--field", "status", "--json"))
    assert [(r["from"], r["to"]) for r in data] == [("To Do", "Done")]
    assert data[0]["author"]["accountId"] == fake_jira.ALICE["accountId"]
    assert "No changes to DEMO-3." in ok("issue", "history", "demo-3")


def test_sprint_issues_take_fields_and_format(site):
    assert ok("sprint", "issues", "7", "--format", "{key} {type}").splitlines() == [
        "DEMO-1 Bug", "DEMO-3 Story",
    ]  # fmt: skip
    data = json.loads(ok("board", "backlog", "1", "--fields", "summary", "--json"))
    assert all(set(row) == {"key", "summary"} for row in data)
