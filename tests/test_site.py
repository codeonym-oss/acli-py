"""Projects, boards, sprints, filters, fields, dashboards, users, meta and the raw API."""

from __future__ import annotations

import json

from tests import fake_jira
from tests.conftest import run_cli


def ok(*args: str, input: str | None = None) -> str:
    result, out = run_cli(*args, input=input)
    assert result.exit_code == 0, out
    return out


# ── projects ─────────────────────────────────────────────────────────────────


def test_project_list_and_view(site):
    out = ok("project", "list")
    assert "DEMO" in out
    assert "Operations" in out
    assert [p["key"] for p in json.loads(ok("project", "list", "-q", "ops", "--json"))] == ["OPS"]
    assert "Demo" in ok("project", "list", "--recent")
    out = ok("project", "view", "demo")
    assert "Alice Martin" in out
    assert "Epic" in out
    assert "API" in ok("project", "components", "DEMO")
    assert "2.4" in ok("project", "versions", "DEMO", "--unreleased")


def test_project_create_update_archive_restore_delete(site):
    template = json.loads(ok("project", "create", "--print-template"))
    assert template["template"] == "kanban"
    ok(
        "project",
        "create",
        "-k",
        "new",
        "--name",
        "New one",
        "-T",
        "scrum",
        "--lead",
        "bob@example.com",
    )
    body = next(b for m, p, b in site.log if m == "POST" and p == "/rest/api/3/project")
    assert body["projectTemplateKey"].endswith("gh-simplified-scrum-classic")
    assert body["leadAccountId"] == fake_jira.BOB["accountId"]
    assert body["projectTypeKey"] == "software"
    assert "NEW" in site.projects
    ok("project", "update", "NEW", "--name", "Renamed", "-y")
    assert site.projects["NEW"]["name"] == "Renamed"
    ok("project", "archive", "NEW", "-y")
    assert site.projects["NEW"]["archived"]
    ok("project", "restore", "NEW", "-y")
    assert not site.projects["NEW"]["archived"]
    result, _ = run_cli("project", "delete", "NEW")
    assert result.exit_code == 2  # declined: there is no terminal to ask on
    ok("project", "delete", "NEW", "-y")
    assert ("DELETE", "/rest/api/3/project/NEW", None) in site.log
    assert "NEW" not in site.projects


def test_project_create_from_json(site, tmp_path):
    spec = tmp_path / "p.json"
    spec.write_text(json.dumps({"key": "biz", "name": "Business", "template": "tasks"}))
    ok("project", "create", "--from-json", str(spec))
    assert site.projects["BIZ"]["projectTypeKey"] == "business"
    _, out = run_cli("project", "create", "--name", "No key")
    assert "needs --key and --name" in out
    _, out = run_cli("project", "update", "DEMO")
    assert "Nothing to change" in out


# ── boards and sprints ───────────────────────────────────────────────────────


def test_boards(site):
    out = ok("board", "list")
    assert "DEMO board" in out
    out = ok("board", "view", "1")
    assert "To Do → Done" in out
    assert "DEMO" in ok("board", "projects", "1")
    assert "Write release notes" in ok("board", "backlog", "1")
    ok("board", "create", "--name", "Ops flow", "--filter", "10100", "-p", "OPS")
    board_id = next(k for k, b in site.boards.items() if b["name"] == "Ops flow")
    ok("board", "delete", board_id, "-y")
    assert board_id not in site.boards
    _, out = run_cli("board", "create", "--name", "x", "--filter", "1", "--type", "list")
    assert "scrum or kanban" in out


def test_sprints_lifecycle(site):
    out = ok("sprint", "list", "1", "--state", "active")
    assert "Sprint 7" in out
    assert "Sprint 8" not in out
    assert "Sprint 8" in ok("board", "sprints", "1")
    assert "Ship login" in ok("sprint", "view", "7")
    out = ok("sprint", "issues", "7")
    assert "DEMO-1" in out
    assert "DEMO-2" not in out

    ok("sprint", "create", "--name", "Sprint 9", "--board", "1", "--start", "2026-10-05",
       "--end", "2026-10-19", "--goal", "Polish")  # fmt: skip
    new = next(s for s in site.sprints.values() if s["name"] == "Sprint 9")
    assert new["endDate"] == "2026-10-19T23:59:00.000Z"

    ok("sprint", "add", "8", "DEMO-2", "-y")
    assert site.issues["DEMO-2"]["sprint"] == 8
    ok("sprint", "remove", "DEMO-2", "-y")
    assert site.issues["DEMO-2"]["sprint"] is None

    result, out = run_cli("sprint", "start", "7", "-y")
    assert result.exit_code == 1
    assert "only a future sprint can start" in out
    ok("sprint", "start", "8", "--start", "2026-10-05", "--weeks", "1", "-y")
    assert site.sprints["8"]["state"] == "active"
    assert site.sprints["8"]["endDate"] == "2026-10-12T00:00:00.000Z"
    ok("sprint", "update", "8", "--name", "Sprint 8b", "-y")
    assert site.sprints["8"]["name"] == "Sprint 8b"
    ok("sprint", "close", "7", "-y")
    assert site.sprints["7"]["state"] == "closed"
    ok("sprint", "delete", "8", "-y")
    assert "8" not in site.sprints


def test_sprint_board_default(site):
    result, out = run_cli("sprint", "list")
    assert result.exit_code == 1
    assert "No board given" in out
    ok("config", "set", "board", "1")
    assert "Sprint 7" in ok("sprint", "list")


# ── filters ──────────────────────────────────────────────────────────────────


def test_filters(site):
    assert "My open work" in ok("filter", "list")
    assert "My open work" in ok("filter", "list", "--favourites")
    assert "My open work" in ok("filter", "search", "-q", "open")
    assert "assignee = currentUser()" in ok("filter", "view", "10100")

    ok("filter", "create", "--name", "Bugs", "--jql", "type = Bug", "--share",
       '[{"type": "project", "project": {"id": "10000"}}]')  # fmt: skip
    new = next(f for f in site.filters.values() if f["name"] == "Bugs")
    assert new["sharePermissions"][0]["type"] == "project"

    ok("filter", "update", new["id"], "--jql", "type = Bug AND project = DEMO", "-y")
    assert new["jql"] == "type = Bug AND project = DEMO"
    assert new["name"] == "Bugs"

    ok("filter", "star", new["id"], "-y")
    assert new["favourite"]
    ok("filter", "star", new["id"], "--remove", "-y")
    assert not new["favourite"]

    ok("filter", "owner", new["id"], "--to", "bob@example.com", "-y")
    assert new["owner"] == fake_jira.BOB

    ok("filter", "columns", "10100", "--set", "summary,status", "-y")
    assert site.filters["10100"]["columns"] == ["summary", "status"]
    assert "Status" in ok("filter", "columns", "10100")
    ok("filter", "columns", "10100", "--reset", "-y")
    assert site.filters["10100"]["columns"] == []

    ok("filter", "delete", new["id"], "-y")
    assert new["id"] not in site.filters
    _, out = run_cli("filter", "create", "--name", "x", "--jql", "y", "--share", "{}")
    assert "JSON array" in out


# ── fields ───────────────────────────────────────────────────────────────────


def test_fields(site):
    out = ok("field", "list", "--custom")
    assert "customfield_10016" in out
    assert "summary" not in out
    assert "Story point estimate" in ok("field", "list", "-q", "story")
    ok("field", "create", "--name", "Risk", "--type", "select")
    body = next(b for m, p, b in site.log if m == "POST" and p == "/rest/api/3/field")
    assert body["type"].endswith(":select")
    assert body["searcherKey"].endswith(":multiselectsearcher")
    _, out = run_cli("field", "create", "--name", "x", "--type", "blob")
    assert "Unknown field type" in out
    ok("field", "update", "customfield_10016", "--name", "Points", "-y")
    ok("field", "delete", "customfield_10030", "-y")
    assert "customfield_10030" in site.trashed_fields
    ok("field", "restore", "customfield_10030", "-y")
    assert not site.trashed_fields


# ── dashboards, users, meta, api ─────────────────────────────────────────────


def test_dashboards_users_and_meta(site):
    assert "Team health" in ok("dashboard", "list", "--owner", "@me")
    assert "Team health" in ok("dashboard", "view", "10200")
    out = ok("user", "search", "jensen")
    assert "Bob Jensen" in out
    assert "Carol Jensen" in out
    assert "jira-users" in ok("user", "view", "bob@example.com")
    assert "Europe/Paris" in ok("user", "view")
    assert "In Progress" in ok("meta", "statuses")
    assert "High" in ok("meta", "priorities")
    assert "Won't Do" in ok("meta", "resolutions")
    assert "Subtask" in ok("meta", "issue-types")
    assert "Epic" not in ok("meta", "issue-types", "-p", "DEMO")


def test_raw_api(site, tmp_path):
    assert json.loads(ok("api", "GET", "myself"))["displayName"] == "Alice Martin"
    found = json.loads(ok("api", "get", "/rest/api/3/user/search", "-q", "query=bob"))
    assert [u["displayName"] for u in found] == ["Bob Jensen"]
    payload = tmp_path / "issue.json"
    payload.write_text(json.dumps({"fields": {"project": {"key": "OPS"}, "summary": "via api"}}))
    created = json.loads(ok("api", "POST", "issue", "-d", f"@{payload}"))
    assert site.issues[created["key"]]["fields"]["summary"] == "via api"
    result, out = run_cli("api", "TRACE", "x")
    assert "Unsupported method" in out
    result, out = run_cli("api", "GET", "issue/NOPE-1")
    assert result.exit_code == 1
    assert "not found" in out


def test_debug_traces_http(site):
    out = ok("--debug", "user", "view")
    assert "HTTP GET 200" in out


def test_project_create_from_another_shares_its_schemes(site):
    result, out = run_cli(
        "project", "create", "-k", "web2", "--name", "Web 2", "--from-project", "demo"
    )
    assert result.exit_code == 0, out
    assert "Sharing DEMO's configuration: permission, notification, issueType" in out
    body = next(b for m, p, b in site.writes() if p == "/rest/api/3/project")
    assert "projectTemplateKey" not in body
    assert body["projectTypeKey"] == "software"
    assert site.projects["WEB2"]["schemes"] == {
        "permissionScheme": 0, "notificationScheme": 10000, "issueTypeScheme": 10010,
        "issueTypeScreenScheme": 10020, "workflowScheme": 10030,
    }  # fmt: skip


def test_project_create_from_a_team_managed_project_is_refused(site):
    site.projects["DEMO"]["style"] = "next-gen"
    result, out = run_cli("project", "create", "-k", "X", "--name", "X", "--from-project", "DEMO")
    assert result.exit_code == 1
    assert "team-managed" in out
