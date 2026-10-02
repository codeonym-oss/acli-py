"""Projects, boards, sprints, filters, fields and dashboards as use cases on the bus."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from acli_py.application.commands.move_to_sprint.command import MoveToSprint
from acli_py.application.commands.update_sprint.command import UpdateSprint
from acli_py.domain.agile import Sprint, SprintState
from acli_py.domain.fields import CUSTOM, FieldInfo, custom_field_type
from acli_py.domain.filters import Filter
from acli_py.domain.projects import ProjectSpec
from acli_py.infrastructure.audit import default_path
from acli_py.infrastructure.jira.agile import stamp
from acli_py.presentation import terminal
from acli_py.presentation.cli import common
from tests import fake_jira
from tests.conftest import run_cli


def ok(*args: str, input: str | None = None) -> str:
    result, out = run_cli(*args, input=input)
    assert result.exit_code == 0, out
    return out


def audit_lines() -> list[dict]:
    return [json.loads(line) for line in default_path().read_text().splitlines()]


# ── the domain ───────────────────────────────────────────────────────────────

NOW = datetime(2026, 10, 1, 9, tzinfo=UTC)


def test_a_sprint_starts_now_for_two_weeks_unless_told():
    sprint = Sprint(8, "Sprint 8")
    assert sprint.schedule(NOW) == (NOW, datetime(2026, 10, 15, 9, tzinfo=UTC))
    start = datetime(2026, 10, 5, tzinfo=UTC)
    assert sprint.schedule(NOW, start, weeks=1) == (start, datetime(2026, 10, 12, tzinfo=UTC))
    planned = Sprint(9, "Sprint 9", start=start, end=datetime(2026, 10, 9, tzinfo=UTC))
    assert planned.schedule(NOW) == (start, datetime(2026, 10, 9, tzinfo=UTC))


def test_only_a_future_sprint_starts():
    with pytest.raises(ValueError, match="Sprint 7 is active; only a future sprint can start"):
        Sprint(7, "Sprint 7", SprintState.ACTIVE).schedule(NOW)


def test_sprint_dates_go_to_jira_in_utc():
    assert stamp(datetime(2026, 10, 5, 11, tzinfo=UTC)) == "2026-10-05T11:00:00.000Z"
    assert stamp(None) is None


def test_a_project_spec_reads_options_and_passes_the_rest_through():
    spec = ProjectSpec.from_mapping({"key": "ops", "name": "Ops", "template": "tasks",
                                     "assigneeType": "PROJECT_LEAD", "lead": None})  # fmt: skip
    assert (spec.key, spec.name, spec.lead) == ("OPS", "Ops", None)
    assert spec.extra == {"assigneeType": "PROJECT_LEAD"}
    assert spec.template_key() == ("business", f"{spec.template_key()[1]}")
    assert ProjectSpec(template="custom:key", type="software").template_key() == (
        "software", "custom:key",
    )  # fmt: skip
    assert ProjectSpec().empty
    assert not ProjectSpec(extra={"x": 1}).empty


def test_custom_field_types_by_name_or_key():
    assert custom_field_type("Number") == (f"{CUSTOM}float", f"{CUSTOM}exactnumber")
    assert custom_field_type("a:b", "s") == ("a:b", "s")
    with pytest.raises(ValueError, match="Unknown field type 'blob'"):
        custom_field_type("blob")


def test_jira_shapes_read_as_domain_objects():
    shared = Filter.from_jira({"id": 1, "name": "F", "sharePermissions": [
        {"type": "group", "group": {"name": "devs"}}, {"type": "project", "project": {"key": "DEMO"}},
        {"type": "global"},
    ]})  # fmt: skip
    assert shared.shared_with == ("devs", "DEMO", "global")
    field = FieldInfo.from_jira({"id": "labels", "name": "Labels",
                                 "schema": {"type": "array", "items": "string"}})  # fmt: skip
    assert (field.type, field.matches("LAB"), field.matches("x")) == ("string[]", True, False)


def test_commands_refuse_changing_nothing():
    with pytest.raises(ValueError, match="Nothing to change"):
        UpdateSprint(8)
    assert str(MoveToSprint("demo-1", 8).change()) == "Move DEMO-1 into sprint 8"
    assert str(MoveToSprint("DEMO-1", None).change()) == "Move DEMO-1 to the backlog"


# ── JSON and pipes ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (["project", "list"], "DEMO\nOPS\n"),
        (["board", "list"], "1\n"),
        (["sprint", "list", "1"], "7\n8\n"),
        (["filter", "list"], "10100\n"),
        (["field", "list", "--custom", "-q", "story"], "customfield_10016\n"),
        (["dashboard", "list"], "10200\n"),
    ],
    ids=lambda c: " ".join(c[:2]) if isinstance(c, list) else "",
)
def test_lists_print_keys_for_pipes(site, command, expected):
    assert ok(*command, "--output", "keys") == expected


def test_views_print_json_from_the_domain(site):
    project = json.loads(ok("project", "view", "DEMO", "--json"))
    assert (project["key"], project["lead"]["name"]) == ("DEMO", "Alice Martin")
    assert [c["name"] for c in project["components"]] == ["API"]
    board = json.loads(ok("board", "view", "1", "--json"))
    assert (board["projectKey"], board["columns"]) == ("DEMO", ["To Do", "Done"])
    sprint = json.loads(ok("sprint", "view", "7", "--json"))
    assert (sprint["state"], sprint["goal"]) == ("active", "Ship login")
    assert sprint["startDate"].startswith("2026-09-21T09:00:00")
    saved = json.loads(ok("filter", "view", "10100", "--json"))
    assert (saved["favourite"], saved["owner"]["name"]) == (True, "Alice Martin")
    assert json.loads(ok("dashboard", "view", "10200", "--json"))["name"] == "Team health"
    (line,) = ok("sprint", "list", "1", "--state", "future", "--output", "jsonl").splitlines()
    assert json.loads(line)["name"] == "Sprint 8"


def test_a_search_pipes_into_a_sprint_asking_once(site):
    keys = ok("issue", "search", "project = DEMO", "--output", "keys")
    out = ok("sprint", "add", "8", "-", "-y", input=keys)
    assert "3 of 3 moved into sprint 8." in out
    assert {site.issues[k]["sprint"] for k in keys.split()} == {8}
    (record,) = audit_lines()
    assert record["command"] == "MoveToSprint"
    assert sorted(record["keys"]) == sorted(keys.split())


def test_an_unknown_sprint_state_is_refused(site):
    result, out = run_cli("sprint", "list", "1", "--state", "done")
    assert result.exit_code == 1
    assert "use future, active or closed" in out


# ── the audit log ────────────────────────────────────────────────────────────


def test_site_changes_keep_what_they_replaced(site):
    ok("project", "update", "DEMO", "--name", "Demo 2", "--lead", "bob@example.com", "-y")
    ok("sprint", "update", "8", "--goal", "Polish", "-y")
    ok("filter", "update", "10100", "--jql", "project = OPS", "-y")
    ok("filter", "columns", "10100", "--set", "summary", "-y")
    project, sprint, saved, columns = audit_lines()
    assert project["changes"] == [{
        "key": "DEMO",
        "before": {"name": "Demo", "lead": fake_jira.ALICE["accountId"]},
        "after": {"name": "Demo 2", "lead": fake_jira.BOB["accountId"]},
    }]  # fmt: skip
    assert sprint["changes"][0] == {"key": "sprint 8", "before": {"goal": ""},
                                    "after": {"goal": "Polish"}}  # fmt: skip
    assert saved["changes"][0]["before"] == {"jql": "project = DEMO AND assignee = currentUser()"}
    assert columns["changes"][0]["before"] == {"columns": ["issuekey", "summary"]}


def test_deleting_several_boards_asks_for_the_count(site, monkeypatch):
    monkeypatch.setattr(common, "interactive", lambda: True)
    asked: list[str] = []
    monkeypatch.setattr(terminal, "answer", lambda q: asked.append(q) or "1")
    ok("board", "create", "--name", "Spare", "--filter", "10100")
    spare = next(k for k, b in site.boards.items() if b["name"] == "Spare")
    result, _ = run_cli("board", "delete", "1", spare)
    assert result.exit_code == 2
    assert asked == ["Delete 2 boards? This can't be undone. Type 2 to agree"]
    assert spare in site.boards
