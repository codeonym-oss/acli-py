"""The everyday helpers: standup, sprint report, git names and aliases."""

from __future__ import annotations

import json
from datetime import date

import pytest
import typer
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from acli_py.domain.helpers import branch_name, commit_message, last_working_day, slug
from acli_py.domain.issue import Issue, IssueType
from acli_py.infrastructure.jira.catalog import JiraCatalog
from acli_py.infrastructure.jira.client import JiraClient
from acli_py.infrastructure.storage import Views
from acli_py.presentation.cli import app
from acli_py.presentation.shell import ShellCompleter
from tests import fake_jira
from tests.conftest import run_cli


def ok(*args: str) -> str:
    result, out = run_cli(*args)
    assert result.exit_code == 0, out
    return out


# ── the rules ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 10, 5), date(2026, 10, 2)),  # Monday → Friday
        (date(2026, 10, 4), date(2026, 10, 2)),  # Sunday → Friday
        (date(2026, 10, 3), date(2026, 10, 2)),  # Saturday → Friday
        (date(2026, 10, 7), date(2026, 10, 6)),  # Wednesday → Tuesday
    ],
)
def test_the_last_working_day(today, expected):
    assert last_working_day(today) == expected


def test_issues_name_branches_and_commits():
    bug = Issue("DEMO-1", "Login fails on Safari 18!", type=IssueType("Bug"))
    task = Issue("DEMO-2", "Write release notes.", type=IssueType("Task"))
    assert branch_name(bug) == "fix/DEMO-1-login-fails-on-safari-18"
    assert branch_name(task, "chore") == "chore/DEMO-2-write-release-notes"
    assert branch_name(task, "") == "DEMO-2-write-release-notes"
    assert commit_message(bug) == "fix: login fails on Safari 18! (DEMO-1)"
    assert commit_message(task) == "feat: write release notes (DEMO-2)"
    assert commit_message(Issue("X-1", "API keys leak", type=IssueType("Bug"))) == (
        "fix: API keys leak (X-1)"
    )
    assert slug("Crème brûlée — à la carte, part 2 of 3 more words", words=6) == (
        "creme-brulee-a-la-carte-part"
    )


# ── standup ──────────────────────────────────────────────────────────────────


def test_standup_lists_what_i_changed_and_what_is_next(site):
    site.changed("DEMO-2", fake_jira.ALICE, ("priority", "Medium", "High"),
                 at="2026-10-01T09:00:00.000+0200")  # fmt: skip
    site.changed("DEMO-3", fake_jira.ALICE, ("labels", "", "x"), at="2026-09-01T09:00:00.000+0200")
    data = json.loads(ok("standup", "--since", "2026-09-30", "--json"))
    assert data["since"] == "2026-09-30"
    assert [i["key"] for i in data["changed"]] == ["DEMO-2"]
    assert [i["key"] for i in data["next"]] == ["DEMO-1", "OPS-1"]
    assert list(data["next"][0]) == ["key", "status", "priority", "summary"]
    lines = ok("standup", "--since", "2026-09-30", "--output", "jsonl").splitlines()
    assert [(row["list"], row["key"]) for row in map(json.loads, lines)] == [
        ("changed", "DEMO-2"), ("next", "DEMO-1"), ("next", "OPS-1"),
    ]  # fmt: skip
    markdown = ok("standup", "--since", "2026-09-30", "--output", "markdown")
    assert "## Changed since Wed 2026-09-30" in markdown
    assert "| DEMO-2 | To Do | Medium | Write release notes |" in markdown
    assert "Next" in ok("standup")
    result, out = run_cli("standup", "--since", "yesterday")
    assert result.exit_code == 1
    assert "not a date" in out


# ── sprint report ────────────────────────────────────────────────────────────


def test_sprint_report_counts_by_status_and_assignee(site):
    site.issues["DEMO-2"]["sprint"] = 7
    site.issues["DEMO-2"]["fields"]["status"] = fake_jira.STATUSES["10001"]
    data = json.loads(ok("sprint", "report", "--board", "1", "--json"))
    assert (data["sprint"]["name"], data["issues"], data["done"]) == ("Sprint 7", 3, 0.333)
    assert data["byStatus"] == [
        {"category": "To Do", "status": "To Do", "issues": 1},
        {"category": "In Progress", "status": "In Progress", "issues": 1},
        {"category": "Done", "status": "Done", "issues": 1},
    ]
    assert {r["assignee"]: r["counts"]["Done"] for r in data["byAssignee"]} == {
        "Alice Martin": 0, "Bob Jensen": 1, "Unassigned": 0,
    }  # fmt: skip
    out = ok("sprint", "report", "7")
    assert "Sprint 7 (active, 2026-09-21 → 2026-10-05): 1 of 3 done, 33%" in out
    assert "Goal: Ship login" in out
    markdown = ok("sprint", "report", "7", "--output", "markdown")
    assert "| Assignee | To Do | In Progress | Done |" in markdown
    assert len(ok("sprint", "report", "7", "--output", "jsonl").splitlines()) == 3


def test_sprint_report_needs_an_active_sprint(site):
    site.sprints["7"]["state"] = "closed"
    result, out = run_cli("sprint", "report", "--board", "1")
    assert result.exit_code == 1
    assert "Board 1 has no active sprint." in out
    assert "The sprint has no issues." in ok("sprint", "report", "8")


# ── git ──────────────────────────────────────────────────────────────────────


def test_git_names_for_an_issue(site):
    assert ok("git", "branch", "demo-1") == "fix/DEMO-1-login-fails-on-safari\n"
    assert ok("git", "branch", "DEMO-2", "--prefix", "docs/") == (
        "docs/DEMO-2-write-release-notes\n"
    )
    assert ok("git", "commit-msg", "DEMO-2") == "feat: write release notes (DEMO-2)\n"
    assert json.loads(ok("git", "branch", "DEMO-1", "--output", "jsonl")) == {
        "key": "DEMO-1",
        "branch": "fix/DEMO-1-login-fails-on-safari",
        "commit": "fix: login fails on Safari (DEMO-1)",
    }


# ── aliases ──────────────────────────────────────────────────────────────────


def test_aliases_run_queries_and_command_lines(site):
    ok("alias", "set", "@web", "labels = web")
    ok("alias", "set", "demo-keys", "issue", "search", "project = DEMO", "--output", "keys")
    assert ok("@web", "--output", "keys") == "DEMO-1\n"
    assert ok("@demo-keys") == "DEMO-1\nDEMO-2\nDEMO-3\n"
    assert ok("@demo-keys", "--limit", "1") == "DEMO-1\n"
    rows = json.loads(ok("alias", "list", "--json"))
    assert {r["name"]: r["kind"] for r in rows if not r["builtin"]} == {
        "web": "query", "demo-keys": "command",
    }  # fmt: skip
    # The TUI shows the query, not the command line.
    assert [v.name for v in Views().saved()] == ["web"]
    ok("alias", "delete", "@web")
    result, out = run_cli("@web")
    assert result.exit_code == 2
    assert "No alias called 'web'" in out
    result, out = run_cli("alias", "delete", "web")
    assert result.exit_code == 1


def test_built_in_views_are_aliases_too_and_complete_in_the_shell(site, fake):
    ok("alias", "set", "mine", "@me is:open")
    _, url = fake
    completer = ShellCompleter(
        typer.main.get_command(app), JiraCatalog(JiraClient(url, fake_jira.EMAIL, fake_jira.TOKEN))
    )
    found = [c.text for c in completer.get_completions(Document("@m"), CompleteEvent())]
    assert found == ["@mine"]
    result, out = run_cli("alias", "set", "two words", "x")
    assert result.exit_code == 1
    assert "one word" in out
