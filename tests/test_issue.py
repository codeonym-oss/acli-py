from __future__ import annotations

import csv
import json

import pytest

from acli_py.domain.adf import to_text
from tests import fake_jira
from tests.conftest import run_cli

BOB = fake_jira.BOB


def ok(*args: str, input: str | None = None) -> str:
    result, out = run_cli(*args, input=input)
    assert result.exit_code == 0, out
    return out


# ── read ─────────────────────────────────────────────────────────────────────


def test_view_shows_details_description_links_and_comments(site):
    out = ok("issue", "view", "demo-1")
    for text in ("DEMO-1", "Login fails on Safari", "Alice Martin", "Steps to reproduce",
                 "Open login", "blocks DEMO-3", "Bob Jensen", "Safari 18"):  # fmt: skip
        assert text in out, text


def test_view_json_and_extra_fields(site):
    data = json.loads(ok("issue", "view", "DEMO-1", "--json"))
    assert data["fields"]["summary"] == "Login fails on Safari"
    out = ok("issue", "view", "DEMO-1", "--fields", "customfield_10016")
    assert "Story point estimate" in out


def test_search_with_shortcuts(site):
    out = ok("issue", "search", "-p", "demo", "-a", "@me")
    assert "DEMO-1" in out
    assert "DEMO-2" not in out
    assert 'project = "DEMO" AND assignee = currentUser() ORDER BY updated DESC' in out


def test_search_json_csv_count_and_fields(site):
    issues = json.loads(ok("issue", "search", "project = DEMO", "--json"))
    assert [i["key"] for i in issues] == ["DEMO-1", "DEMO-2", "DEMO-3"]
    rows = list(csv.reader(ok("issue", "search", "-p", "DEMO", "--csv").splitlines()))
    assert rows[0] == ["Key", "Type", "Status", "Priority", "Assignee", "Summary"]
    assert rows[1][0] == "DEMO-1"
    assert json.loads(ok("issue", "search", "-p", "DEMO", "--count", "--json"))["count"] == 3
    out = ok("issue", "search", "-p", "DEMO", "--fields", "summary,labels")
    assert "labels" in out
    assert "web" in out


def test_search_limit_and_saved_filter(site):
    out = ok("issue", "list", "-p", "DEMO", "--limit", "1")
    assert "use --all" in out
    out = ok("issue", "search", "--filter", "10100")
    assert "DEMO-1" in out
    assert "OPS-1" not in out


def test_search_needs_something_to_search_for(site):
    result, out = run_cli("issue", "search")
    assert result.exit_code == 1
    assert "Say what to search" in out
    ok("config", "set", "project", "OPS")
    assert "OPS-1" in ok("issue", "search")


def test_build_jql_combines_everything(site):
    from acli_py.presentation.cli.common import connect
    from acli_py.presentation.cli.issue import build_jql

    session = connect()
    jql = build_jql(
        session,
        jql="labels = web ORDER BY created",
        status=["To Do,In Progress"],
        issue_type=["Bug"],
        label=['a"b'],
        text="safari",
        open_only=True,
        assignee="none",
    )
    assert jql == (
        '(labels = web) AND assignee is EMPTY AND status in ("To Do", "In Progress") '
        'AND issuetype = "Bug" AND labels = "a\\"b" AND text ~ "safari" '
        "AND statusCategory != Done ORDER BY created"
    )
    assert build_jql(session, project="X", order="-created").endswith("ORDER BY created DESC")
    assert f'assignee = "{BOB["accountId"]}"' in build_jql(session, assignee="bob@example.com")


def test_transitions_list(site):
    out = ok("issue", "transitions", "DEMO-1")
    assert "Start work" in out
    assert "Reopen" not in out


# ── create ───────────────────────────────────────────────────────────────────


def test_create_with_every_kind_of_field(site):
    out = ok(
        "issue", "create", "-p", "DEMO", "-t", "Bug", "-s", "Crash on save",
        "-d", "It **crashes**.\n\n- step one", "-a", "bob@example.com", "-P", "High",
        "-L", "web,urgent", "-L", "ios", "--due", "2026-12-01", "--parent", "DEMO-3",
        "-F", "Story point estimate=5", "-F", "Team=Blue", "-F", "Notes=see *log*",
        "-F", "Reviewers=@me,Carol", "-F", "customfield_10016:=8",
    )  # fmt: skip
    assert "Created DEMO-4" in out
    fields = site.issues["DEMO-4"]["fields"]
    assert fields["issuetype"]["name"] == "Bug"
    assert fields["assignee"] == BOB
    assert fields["priority"]["name"] == "High"
    assert fields["labels"] == ["web", "urgent", "ios"]
    assert fields["duedate"] == "2026-12-01"
    assert fields["parent"]["key"] == "DEMO-3"
    assert fields["customfield_10016"] == 8  # the raw := assignment came last
    assert fields["customfield_10020"] == {"value": "Blue"}
    assert fields["customfield_10030"]["type"] == "doc"
    assert [u["accountId"] for u in fields["customfield_10040"]] == [
        fake_jira.ALICE["accountId"], fake_jira.CAROL["accountId"],
    ]  # fmt: skip
    assert to_text(fields["description"]) == "It **crashes**.\n\n- step one"


def test_create_uses_configured_defaults(site):
    ok("config", "set", "project", "OPS")
    ok("config", "set", "issue-type", "Story")
    ok("issue", "create", "-s", "Defaults")
    assert site.issues["OPS-2"]["fields"]["issuetype"]["name"] == "Story"


def test_create_needs_a_summary_and_a_project(site):
    result, out = run_cli("issue", "create", "-p", "DEMO")
    assert result.exit_code == 1
    assert "summary is required" in out
    result, out = run_cli("issue", "create", "-s", "x")
    assert result.exit_code == 1
    assert "No project given" in out


def test_create_reports_unknown_fields_helpfully(site):
    result, out = run_cli("issue", "create", "-p", "DEMO", "-s", "x", "-F", "Story=3")
    assert result.exit_code == 1
    assert "Did you mean: Story point estimate" in out
    result, out = run_cli(
        "issue", "create", "-p", "DEMO", "-s", "x", "-F", "Story point estimate=lots"
    )
    assert "takes a number" in out
    result, out = run_cli("issue", "create", "-p", "DEMO", "-s", "x", "-a", "nobody-matches")
    assert "no user matches" in out
    result, out = run_cli("issue", "create", "-p", "DEMO", "-s", "x", "-a", "Jensen")
    assert "matches several people" in out


def test_create_dry_run_sends_nothing(site):
    out = ok("issue", "create", "-p", "DEMO", "-s", "Preview me", "-a", "@me", "--dry-run")
    assert "DRY RUN POST /rest/api/3/issue" in out
    assert '"summary": "Preview me"' in out
    assert "1 change planned, nothing was sent" in out
    assert site.writes() == []
    assert "DEMO-4" not in site.issues


def test_global_dry_run_and_environment_variable(site, monkeypatch):
    ok("--dry-run", "issue", "create", "-p", "DEMO", "-s", "x")
    monkeypatch.setenv("ACLI_PY_DRY_RUN", "1")
    ok("issue", "create", "-p", "DEMO", "-s", "y")
    assert site.writes() == []


def test_create_many_from_json_and_csv(site, tmp_path):
    template = json.loads(ok("issue", "create", "--template"))
    assert template[0]["summary"]
    rows = [
        {"summary": "From JSON", "type": "Story", "labels": ["a", "b"], "fields": {"Team": "Red"}},
        {
            "fields": {
                "project": {"key": "OPS"},
                "summary": "Raw payload",
                "issuetype": {"name": "Task"},
            }
        },
    ]
    path = tmp_path / "issues.json"
    path.write_text(json.dumps(rows))
    out = ok("issue", "create", "--from-json", str(path), "-p", "DEMO", "-y")
    assert "2 of 2 created" in out
    assert site.issues["DEMO-4"]["fields"]["customfield_10020"] == {"value": "Red"}
    assert site.issues["DEMO-4"]["fields"]["labels"] == ["a", "b"]
    assert site.issues["OPS-2"]["fields"]["summary"] == "Raw payload"

    sheet = tmp_path / "issues.csv"
    sheet.write_text(
        "summary,projectKey,issueType,label,Story point estimate\n"
        "First,DEMO,Bug,x;y,2\nSecond,OPS,,,\n"
    )
    out = ok("issue", "create", "--from-csv", str(sheet), "-y")
    assert "2 of 2 created" in out
    assert site.issues["DEMO-5"]["fields"]["labels"] == ["x", "y"]
    assert site.issues["DEMO-5"]["fields"]["customfield_10016"] == 2
    assert site.issues["OPS-3"]["fields"]["issuetype"]["name"] == "Task"


def test_create_many_stops_at_the_first_error_unless_told_not_to(site, tmp_path):
    path = tmp_path / "issues.json"
    path.write_text(json.dumps([{"summary": "a", "type": "Nope"}, {"summary": "b"}]))
    result, out = run_cli("issue", "create", "--from-json", str(path), "-p", "DEMO", "-y")
    assert result.exit_code == 1
    assert "1 not tried" in out
    result, out = run_cli(
        "issue", "create", "--from-json", str(path), "-p", "DEMO", "-y", "--ignore-errors", "--json"
    )
    assert result.exit_code == 1
    assert "1 of 2 created, 1 failed" in out


def test_create_many_asks_first_without_a_terminal(site, tmp_path):
    path = tmp_path / "issues.json"
    path.write_text(json.dumps([{"summary": "a"}]))
    result, out = run_cli("issue", "create", "--from-json", str(path), "-p", "DEMO")
    assert result.exit_code == 1
    assert "Refusing without --yes" in out
    assert site.writes() == []


def test_create_with_editor(site, tmp_path, monkeypatch):
    script = tmp_path / "fake-editor.py"
    script.write_text(
        "import sys, pathlib\n"
        "pathlib.Path(sys.argv[1]).write_text('Edited title\\n\\nEdited **body**\\n')\n"
    )
    import sys

    monkeypatch.setenv("EDITOR", f"{sys.executable} {script}")
    ok("issue", "create", "-p", "DEMO", "--editor")
    fields = site.issues["DEMO-4"]["fields"]
    assert fields["summary"] == "Edited title"
    assert to_text(fields["description"]) == "Edited **body**"


# ── change ───────────────────────────────────────────────────────────────────


def test_edit_fields_and_labels(site):
    ok("issue", "edit", "DEMO-1", "-s", "New title", "--add-label", "urgent",
       "--remove-label", "web", "-a", "none", "-F", "Story point estimate=13")  # fmt: skip
    fields = site.issues["DEMO-1"]["fields"]
    assert fields["summary"] == "New title"
    assert fields["labels"] == ["urgent"]
    assert fields["assignee"] is None
    assert fields["customfield_10016"] == 13


def test_edit_many_by_jql_needs_confirmation(site):
    result, out = run_cli("issue", "edit", "--jql", "project = DEMO", "--add-label", "q4")
    assert result.exit_code == 1
    assert "Edit 3 issues?" in out
    out = ok("issue", "edit", "--jql", "project = DEMO", "--add-label", "q4", "-y")
    assert "3 of 3 edited" in out
    assert all("q4" in site.issues[f"DEMO-{n}"]["fields"]["labels"] for n in (1, 2, 3))


def test_edit_needs_something_to_change(site):
    result, out = run_cli("issue", "edit", "DEMO-1")
    assert result.exit_code == 1
    assert "Nothing to change" in out
    result, out = run_cli("issue", "edit", "-s", "x")
    assert "say which issues" in out
    result, out = run_cli("issue", "edit", "not-a-key", "-s", "x")
    assert "is not an issue key" in out


def test_edit_from_file_of_keys(site, tmp_path):
    keys = tmp_path / "keys.txt"
    keys.write_text("DEMO-1, DEMO-2\n# a comment\nDEMO-3\n")
    out = ok("issue", "edit", "--from-file", str(keys), "-P", "Low", "-y")
    assert "3 of 3 edited" in out


def test_assign_and_unassign(site):
    ok("issue", "assign", "DEMO-2", "--to", "@me")
    assert site.issues["DEMO-2"]["fields"]["assignee"] == fake_jira.ALICE
    ok("issue", "assign", "DEMO-2", "--to", "default")
    assert site.issues["DEMO-2"]["fields"]["assignee"] == BOB
    ok("issue", "assign", "DEMO-2", "--unassign")
    assert site.issues["DEMO-2"]["fields"]["assignee"] is None
    result, _ = run_cli("issue", "assign", "DEMO-2")
    assert result.exit_code == 1


def test_transition_by_status_or_transition_name(site):
    out = ok("issue", "transition", "DEMO-1", "--to", "in progress", "-m", "Starting")
    assert "moved to In Progress" in out
    assert site.issues["DEMO-1"]["fields"]["status"]["name"] == "In Progress"
    assert to_text(site.issues["DEMO-1"]["comments"][-1]["body"]) == "Starting"
    ok("issue", "move", "DEMO-1", "--to", "Finish", "--resolution", "Done")
    assert site.issues["DEMO-1"]["fields"]["status"]["name"] == "Done"
    assert site.issues["DEMO-1"]["fields"]["resolution"] == {"name": "Done"}


def test_transition_explains_what_is_possible(site):
    result, out = run_cli("issue", "transition", "DEMO-1", "--to", "Nowhere")
    assert result.exit_code == 1
    assert "Available: Start work → In Progress, Finish → Done" in out
    result, out = run_cli("issue", "transition", "DEMO-1")
    assert "Say where to" in out


def test_delete_asks_then_deletes(site):
    result, out = run_cli("issue", "delete", "DEMO-2")
    assert result.exit_code == 1
    assert "Permanently delete 1 issue (DEMO-2)?" in out
    assert "DEMO-2" in site.issues
    ok("issue", "delete", "DEMO-2", "--yes")
    assert "DEMO-2" not in site.issues


def test_delete_with_subtasks(site):
    sub = site.add_issue("DEMO", "child", "Subtask")
    sub["fields"]["parent"] = {"key": "DEMO-2"}
    result, out = run_cli("issue", "delete", "DEMO-2", "-y")
    assert result.exit_code == 1
    assert "has subtasks" in out
    ok("issue", "delete", "DEMO-2", "-y", "--with-subtasks")
    assert sub["key"] not in site.issues


def test_archive_and_unarchive(site):
    result, out = run_cli("issue", "archive", "DEMO-2", "NOPE-9", "-y")
    assert result.exit_code == 1
    assert "DEMO-2 archived" in out
    assert "NOPE-9 could not be archived" in out
    assert site.issues["DEMO-2"]["archived"]
    ok("issue", "unarchive", "DEMO-2", "-y")
    assert not site.issues["DEMO-2"]["archived"]


def test_clone_copies_and_links(site):
    out = ok("issue", "clone", "DEMO-1", "--prefix", "Copy: ")
    assert "cloned as DEMO-4" in out
    copy = site.issues["DEMO-4"]["fields"]
    assert copy["summary"] == "Copy: Login fails on Safari"
    assert copy["labels"] == ["web"]
    assert any(
        link == {"type": "Cloners", "outward": "DEMO-4", "inward": "DEMO-1"}
        for link in site.links.values()
    )
    ok("issue", "clone", "DEMO-1", "-p", "OPS", "--no-link")
    assert site.issues["OPS-2"]["fields"]["summary"] == "Login fails on Safari"


@pytest.mark.parametrize(
    "command",
    [
        ["issue", "edit", "DEMO-1", "-s", "x", "--add-label", "y"],
        ["issue", "edit", "--jql", "project = DEMO", "-P", "Low"],
        ["issue", "assign", "DEMO-1", "--to", "bob@example.com"],
        ["issue", "transition", "DEMO-1", "--to", "Done"],
        ["issue", "delete", "DEMO-1", "DEMO-2"],
        ["issue", "archive", "DEMO-1"],
        ["issue", "unarchive", "DEMO-1"],
        ["issue", "clone", "DEMO-1"],
        ["issue", "comment", "add", "DEMO-1", "-b", "hi"],
        ["issue", "comment", "edit", "DEMO-1", "1", "-b", "hi"],
        ["issue", "comment", "delete", "DEMO-1", "1"],
        ["issue", "link", "add", "DEMO-1", "relates to", "DEMO-2"],
        ["issue", "link", "delete", "123"],
        ["issue", "watcher", "add", "DEMO-1", "bob@example.com"],
        ["issue", "watcher", "remove", "DEMO-1"],
        ["issue", "worklog", "add", "DEMO-1", "1h"],
        ["issue", "worklog", "delete", "DEMO-1", "5"],
        ["issue", "attachment", "delete", "5"],
        ["project", "create", "-k", "NEW", "--name", "New"],
        ["project", "update", "DEMO", "--name", "Renamed"],
        ["project", "delete", "DEMO"],
        ["project", "delete", "DEMO", "--permanent"],
        ["project", "archive", "DEMO"],
        ["project", "restore", "DEMO"],
        ["board", "create", "--name", "B", "--filter", "10100"],
        ["board", "delete", "1"],
        ["sprint", "create", "--name", "S", "--board", "1"],
        ["sprint", "update", "8", "--goal", "g"],
        ["sprint", "start", "8"],
        ["sprint", "close", "7"],
        ["sprint", "delete", "8"],
        ["sprint", "add", "8", "DEMO-2"],
        ["sprint", "remove", "DEMO-1"],
        ["filter", "create", "--name", "F", "--jql", "project = DEMO"],
        ["filter", "update", "10100", "--name", "G"],
        ["filter", "delete", "10100"],
        ["filter", "star", "10100", "--remove"],
        ["filter", "owner", "10100", "--to", "bob@example.com"],
        ["filter", "columns", "10100", "--set", "summary"],
        ["filter", "columns", "10100", "--reset"],
        ["field", "create", "--name", "F", "--type", "number"],
        ["field", "update", "customfield_10016", "--name", "Points"],
        ["field", "delete", "customfield_10016"],
        ["field", "restore", "customfield_10016"],
        ["api", "DELETE", "issue/DEMO-1"],
    ],
    ids=lambda c: " ".join(c[:3]),
)
def test_every_write_command_honours_dry_run(site, command):
    result, out = run_cli(*command, "--dry-run")
    assert result.exit_code == 0, out
    assert "DRY RUN" in out
    assert "nothing was sent to Jira" in out
    assert site.writes() == [], site.writes()
