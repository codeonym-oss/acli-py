"""Field edits: `edit_issue`, `assign_issue` and `watch_issue`, from the domain to the CLI."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from mediary import Mediator

from acli_py.application.audit import AuditTrail
from acli_py.application.behaviors import Confirm
from acli_py.application.bulk import Bulk
from acli_py.application.changes import AuditRecord, Change, Changed, PreviewRow
from acli_py.application.commands import assign_issue, edit_issue, watch_issue
from acli_py.application.commands.assign_issue.command import AssignIssue
from acli_py.application.commands.edit_issue.command import EditIssue
from acli_py.application.commands.watch_issue.command import WatchIssue
from acli_py.application.messages import SearchIssues
from acli_py.application.ports import IssueEditor, Watchers
from acli_py.application.site import Site
from acli_py.bootstrap import build_bus
from acli_py.domain import edits
from acli_py.infrastructure.audit import default_path
from acli_py.infrastructure.jira.client import JiraClient
from acli_py.presentation import terminal
from acli_py.presentation.cli import common
from tests import fake_jira
from tests.conftest import run_cli

ALICE, BOB = fake_jira.ALICE["accountId"], fake_jira.BOB["accountId"]


# ── domain ───────────────────────────────────────────────────────────────────


def test_after_applies_set_add_and_remove():
    assert edits.after(["web"], [{"add": "ui"}, {"add": "web"}, {"remove": "old"}]) == [
        "web", "ui",
    ]  # fmt: skip
    assert edits.after(None, [{"set": ["a"]}, {"add": "b"}]) == ["a", "b"]
    parts = [{"name": "API", "id": "1"}, {"name": "UI", "id": "2"}]
    assert edits.after(parts, [{"remove": {"id": "1"}}]) == [{"name": "UI", "id": "2"}]
    assert edits.after(parts, [{"add": {"name": "API"}}]) == parts
    assert edits.after(["x"], [{"set": None}]) == []


def test_operations_read_as_short_text():
    ops = [{"add": "web"}, {"remove": "old"}, {"set": [{"name": "API"}]}]
    assert edits.operations_text(ops) == "+web −old = API"
    assert edits.operations_text([{"set": []}]) == "= none"


# ── the commands say what they change ────────────────────────────────────────


def test_edits_read_as_sentences():
    edit = EditIssue("demo-1", {"priority": {"name": "High"}, "summary": "x" * 40})
    assert str(edit.change()) == f"Edit DEMO-1: priority → High, summary → {'x' * 29}…"
    labels = EditIssue.labelling("DEMO-1", ["web"], ["old"])
    assert str(labels.change()) == "Edit DEMO-1: labels +web −old"
    assert str(EditIssue("DEMO-1").change()) == "Edit DEMO-1"
    assert (
        str(EditIssue.setting("DEMO-1", "duedate", None).change()) == "Edit DEMO-1: duedate → none"
    )
    assert EditIssue.labelling("DEMO-1").update == {}


def test_edits_preview_one_field_only():
    labels = EditIssue.labelling("DEMO-1", ["ui"], ["web"])
    assert (labels.previews(), labels.after(["web", "safari"])) == ("labels", "safari, ui")
    priority = EditIssue.setting("DEMO-1", "priority", {"name": "High"})
    assert (priority.previews(), priority.after({"name": "Low"})) == ("priority", "High")
    both = EditIssue("DEMO-1", {"summary": "x"}, {"labels": [{"add": "y"}]})
    assert both.previews() is None
    replaced = EditIssue("DEMO-1", {"labels": ["a"]}, {"labels": [{"add": "b"}]})
    assert replaced.after(["z"]) == "a"  # a field set outright wins


def test_assignments_and_watches_read_as_sentences():
    assert str(AssignIssue("demo-1", BOB, "Bob").change()) == "Assign DEMO-1 to Bob"
    assert str(AssignIssue("DEMO-1", BOB).change()) == f"Assign DEMO-1 to {BOB}"
    assert str(AssignIssue("DEMO-1", "-1").change()) == "Assign DEMO-1 to the default assignee"
    assert str(AssignIssue("DEMO-1", None).change()) == "Unassign DEMO-1"
    assert AssignIssue("DEMO-1", None).after({"accountId": BOB}) == ""
    assert AssignIssue("DEMO-1", BOB, "Bob").after(None) == "Bob"
    assert str(WatchIssue("demo-1", ALICE).change()) == "Watch DEMO-1"
    assert str(WatchIssue("DEMO-1", ALICE, False).change()) == "Stop watching DEMO-1"
    assert str(WatchIssue("DEMO-1", BOB, True, "Bob").change()) == "Make Bob watch DEMO-1"
    assert str(WatchIssue("DEMO-1", BOB, False, "Bob").change()) == "Make Bob stop watching DEMO-1"


# ── handlers, over stub ports ────────────────────────────────────────────────


class StubEditor:
    """An `IssueEditor` in memory, recording what it was asked to do."""

    def __init__(self, **values: Any) -> None:
        self.fields = dict(values)
        self.done: list[tuple] = []

    def values(self, key: str, field_ids: tuple[str, ...]) -> dict[str, Any]:
        return {f: self.fields.get(f) for f in field_ids}

    def edit(self, key: str, fields: Any, update: Any, *, notify: bool = True) -> None:
        self.done.append(("edit", key, dict(fields), dict(update), notify))

    def assign(self, key: str, account_id: str | None) -> None:
        self.done.append(("assign", key, account_id))


class StubWatchers:
    """A `Watchers` in memory."""

    def __init__(self, *watching: str) -> None:
        self.who = set(watching)
        self.calls = 0

    def watching(self, key: str, account_id: str) -> bool:
        return account_id in self.who

    def watch(self, key: str, account_id: str, *, watch: bool = True) -> None:
        self.calls += 1
        (self.who.add if watch else self.who.discard)(account_id)


def send_with(package: Any, port: type, adapter: Any, command: Any) -> Any:
    """Send `command` through a mediator that knows only `package`, with `adapter` as `port`."""

    class Resolver:
        def resolve(self, cls: Any, /) -> Any:
            assert cls is port
            return adapter

    mediator = Mediator(resolver=Resolver())
    mediator.scan(package)
    return asyncio.run(mediator.send(command))


def test_edit_reads_first_then_edits_and_assigns_apart():
    editor = StubEditor(labels=["web"], priority={"name": "Low"}, assignee=None)
    command = EditIssue(
        " demo-1 ",
        {"priority": {"name": "High"}, "assignee": {"accountId": BOB, "displayName": "Bob"}},
        {"labels": [{"add": "ui"}]},
        notify=False,
    )
    changed = send_with(edit_issue, IssueEditor, editor, command)
    assert changed.key == "DEMO-1"
    assert changed.before == {"priority": {"name": "Low"}, "assignee": None, "labels": ["web"]}
    assert changed.after["labels"] == ["web", "ui"]
    assert changed.after["priority"] == {"name": "High"}
    assert editor.done == [
        ("edit", "DEMO-1", {"priority": {"name": "High"}}, {"labels": [{"add": "ui"}]}, False),
        ("assign", "DEMO-1", BOB),
    ]


def test_an_empty_edit_asks_nothing_and_sends_nothing():
    editor = StubEditor()
    assert send_with(edit_issue, IssueEditor, editor, EditIssue("DEMO-1")) == Changed("DEMO-1")
    assert editor.done == []


def test_assign_keeps_who_had_it():
    editor = StubEditor(assignee={"accountId": ALICE, "displayName": "Alice"})
    changed = send_with(assign_issue, IssueEditor, editor, AssignIssue("demo-1", None))
    assert changed == Changed("DEMO-1", {"assignee": ALICE}, {"assignee": None})
    assert editor.done == [("assign", "DEMO-1", None)]
    changed = send_with(assign_issue, IssueEditor, StubEditor(), AssignIssue("DEMO-1", BOB))
    assert changed.before == {"assignee": None}


def test_watch_changes_only_what_needs_to():
    watchers = StubWatchers(ALICE)
    changed = send_with(watch_issue, Watchers, watchers, WatchIssue("demo-1", ALICE))
    assert changed.before["watching"] is changed.after["watching"] is True
    assert watchers.calls == 0  # already watching: nothing sent
    changed = send_with(watch_issue, Watchers, watchers, WatchIssue("DEMO-1", ALICE, False))
    assert changed.before == {"watcher": ALICE, "watching": True}
    assert changed.after == {"watcher": ALICE, "watching": False}
    assert watchers.who == set()


# ── on the fake site, through the bus ────────────────────────────────────────


class Kept:
    """An `AuditLog` in memory."""

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def record(self, entry: AuditRecord) -> None:
        self.records.append(entry)


def fake_bus(url: str, audit: Kept) -> Any:
    client = JiraClient(url, fake_jira.EMAIL, fake_jira.TOKEN, retries=0)
    return build_bus(Site(client, url), assume_yes=True, audit=audit)


def test_the_audit_log_keeps_what_each_edit_replaced(site, fake):
    audit = Kept()
    bus = fake_bus(fake[1], audit)
    commands = [EditIssue.labelling(k, ["q4"], ["web"]) for k in ("DEMO-1", "DEMO-2")]
    asyncio.run(bus.bulk.run(commands))
    asyncio.run(bus.send(EditIssue.setting("DEMO-1", "priority", {"name": "High"})))
    asyncio.run(bus.send(AssignIssue("DEMO-2", None)))
    asyncio.run(bus.send(WatchIssue("DEMO-2", BOB, True, "Bob")))
    labels, priority, assign, watch = audit.records
    assert labels.command == "EditIssue"
    assert {c.key: (c.before["labels"], c.after["labels"]) for c in labels.changes} == {
        "DEMO-1": (["web"], ["q4"]),
        "DEMO-2": (["docs"], ["docs", "q4"]),
    }
    (changed,) = priority.changes
    assert changed.before["priority"]["name"] == "Medium"
    assert changed.after == {"priority": {"name": "High"}}
    assert assign.changes == (Changed("DEMO-2", {"assignee": BOB}, {"assignee": None}),)
    assert watch.changes[0].after == {"watcher": BOB, "watching": True}
    assert fake_jira.BOB in site.issues["DEMO-2"]["watchers"]
    assert site.issues["DEMO-1"]["fields"]["priority"]["name"] == "High"


def test_the_preview_shows_each_issue_now_and_after(site, fake):
    bus = fake_bus(fake[1], Kept())
    commands = [AssignIssue(k, BOB, "Bob") for k in ("DEMO-1", "DEMO-3")]
    assert asyncio.run(bus.bulk.preview(commands)) == (
        PreviewRow("DEMO-1", "Login fails on Safari", "Alice Martin", "Bob"),
        PreviewRow("DEMO-3", "Speed up search", "", "Bob"),
    )
    mixed = [EditIssue.setting("DEMO-1", "priority", {"name": "High"}), *commands]
    assert asyncio.run(bus.bulk.preview(mixed)) == ()  # different fields: no preview


def test_a_failing_preview_still_asks():
    asked: list[Change] = []

    class Yes:
        async def confirm(self, change: Change) -> bool:
            asked.append(change)
            return True

    async def send(message: Any) -> Any:
        if isinstance(message, SearchIssues):
            raise RuntimeError("the search failed")
        return Changed(message.key)

    bulk = Bulk(send, Confirm(Yes(), lambda: False), AuditTrail(Kept()), lambda: False)
    report = asyncio.run(bulk.run([AssignIssue("DEMO-1", None)]))
    assert report.exit_code == 0
    (change,) = asked
    assert (str(change), change.preview) == ("Unassign DEMO-1", ())


# ── the CLI ──────────────────────────────────────────────────────────────────


def audit_lines() -> list[dict]:
    return [json.loads(line) for line in default_path().read_text().splitlines()]


def test_cli_edit_from_a_pipe_keeps_the_old_values(site):
    piped = '{"key": "DEMO-1"}\n{"key": "DEMO-2"}\n'
    result, out = run_cli("issue", "edit", "-", "-P", "Low", "--no-notify", "-y", input=piped)
    assert result.exit_code == 0, out
    assert "2 of 2 edited." in out
    assert sorted(path for _, path, _ in site.writes()) == [
        "/rest/api/3/issue/DEMO-1", "/rest/api/3/issue/DEMO-2",
    ]  # fmt: skip
    (record,) = audit_lines()
    assert record["command"] == "EditIssue"
    assert {c["key"]: c["before"]["priority"]["name"] for c in record["changes"]} == {
        "DEMO-1": "Medium", "DEMO-2": "Medium",
    }  # fmt: skip


def test_cli_edit_shows_the_preview_then_asks(site, monkeypatch):
    monkeypatch.setattr(common, "interactive", lambda: True)
    asked: list[str] = []
    monkeypatch.setattr(terminal, "ask", lambda q: asked.append(q) or False)
    result, out = run_cli("issue", "edit", "DEMO-1", "DEMO-2", "--add-label", "q4")
    assert result.exit_code == 2
    assert asked == ["Edit 2 issues (DEMO-1, DEMO-2): labels +q4?"]
    assert "web, q4" in out
    assert "docs, q4" in out
    assert site.writes() == []


def test_cli_assign_sets_the_assignee_through_edit(site):
    result, out = run_cli("issue", "edit", "DEMO-3", "-a", "bob@example.com", "-y")
    assert result.exit_code == 0, out
    assert site.issues["DEMO-3"]["fields"]["assignee"] == fake_jira.BOB
    assert [path for _, path, _ in site.writes()] == ["/rest/api/3/issue/DEMO-3/assignee"]


def test_cli_edit_and_assign_with_nothing_picked(site):
    result, out = run_cli("issue", "edit", "-", "-P", "Low", "-y", input="")
    assert (result.exit_code, "nothing to edit" in out) == (0, True)
    result, out = run_cli("issue", "assign", "-", "--to", "@me", "-y", input="")
    assert (result.exit_code, "nothing to assign" in out) == (0, True)


def test_cli_assign_many_from_a_query(site):
    result, out = run_cli("issue", "assign", "--jql", "project = DEMO", "--to", "@me", "-y")
    assert result.exit_code == 0, out
    assert "3 of 3 assigned." in out
    assert "DEMO-3 assigned to @me" in out
    assert all(site.issues[f"DEMO-{n}"]["fields"]["assignee"] == fake_jira.ALICE for n in (1, 2, 3))
    (record,) = audit_lines()
    assert {c["key"]: c["before"]["assignee"] for c in record["changes"]} == {
        "DEMO-1": ALICE, "DEMO-2": BOB, "DEMO-3": None,
    }  # fmt: skip


def test_cli_watch_and_unwatch_many(site):
    result, out = run_cli("issue", "watch", "DEMO-2", "DEMO-3", "-u", "bob@example.com", "-y")
    assert result.exit_code == 0, out
    assert "DEMO-2 now watched by bob@example.com" in out
    assert all(fake_jira.BOB in site.issues[k]["watchers"] for k in ("DEMO-2", "DEMO-3"))
    result, out = run_cli("issue", "unwatch", "-", "-y", input="DEMO-1\n")
    assert result.exit_code == 0, out
    assert "DEMO-1 no longer watched" in out
    assert site.issues["DEMO-1"]["watchers"] == []
    result, out = run_cli("issue", "watch", "-", "-y", input="")
    assert "nothing to watch" in out
    result, out = run_cli("issue", "unwatch", "-", "-y", input="")
    assert "No issues match." in out


def test_cli_dry_run_edits_nothing_and_keeps_nothing(site):
    result, out = run_cli("--dry-run", "issue", "edit", "DEMO-1", "-s", "Renamed")
    assert result.exit_code == 0, out
    assert "would be edited" in out
    assert site.writes() == []
    assert not default_path().exists()


@pytest.mark.parametrize("args", [["--to", "@me", "--unassign"], []])
def test_cli_assign_needs_one_of_to_and_unassign(site, args):
    result, out = run_cli("issue", "assign", "DEMO-1", *args)
    assert result.exit_code == 1
    assert "exactly one of" in out
