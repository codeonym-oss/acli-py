"""The issue lifecycle: `create_issue`, `clone_issue`, `delete_issue` and `archive_issue`."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from mediary import Mediator

from acli_py.application.behaviors import Confirm
from acli_py.application.bulk import change_of
from acli_py.application.changes import Change, PreviewRow
from acli_py.application.commands import archive_issue, clone_issue, create_issue, delete_issue
from acli_py.application.commands.archive_issue.command import ArchiveIssue
from acli_py.application.commands.clone_issue.command import CloneIssue
from acli_py.application.commands.create_issue.command import CreateIssue
from acli_py.application.commands.delete_issue.command import DeleteIssue
from acli_py.application.ports import Destination, IssueEditor, IssueLinks, IssueReader, IssueStore
from acli_py.domain.copies import copy_of
from acli_py.domain.links import IssueLink, LinkType
from acli_py.infrastructure.audit import default_path
from acli_py.infrastructure.jira.fields import parse_rows
from acli_py.infrastructure.jira.resolve import ResolveError
from acli_py.presentation import terminal
from acli_py.presentation.cli import common
from tests.conftest import run_cli

ORIGINAL = {
    "project": {"key": "DEMO"},
    "summary": "Login fails",
    "issuetype": {"name": "Bug"},
    "priority": {"name": "High", "id": "2"},
    "labels": ["web"],
    "components": [{"id": "10", "name": "API"}],
    "fixVersions": [{"id": "20", "name": "2.4"}],
    "parent": {"key": "DEMO-3", "fields": {}},
    "description": None,
}


# ── domain: what a copy takes ────────────────────────────────────────────────


def test_a_copy_keeps_project_parts_only_in_its_project():
    same = copy_of(ORIGINAL, prefix="Copy: ")
    assert same["summary"] == "Copy: Login fails"
    assert same["priority"] == {"name": "High"}
    assert same["components"] == [{"id": "10"}]
    assert same["parent"] == {"key": "DEMO-3"}
    assert "description" not in same  # empty fields aren't copied
    moved = copy_of(ORIGINAL, project="ops")
    assert moved["project"] == {"key": "OPS"}
    assert not {"components", "fixVersions", "parent"} & set(moved)
    assert "components" not in copy_of(ORIGINAL, same_site=False)


# ── the commands say what they change ────────────────────────────────────────


def test_lifecycle_changes_read_as_sentences():
    create = CreateIssue.of("demo", "Bug", " Login fails ", labels=("web",))
    assert str(create.change()) == 'Create a Bug in DEMO: "Login fails"'
    assert create.preview_row() == PreviewRow("#1", "Login fails", "", "Bug in DEMO")
    assert str(CloneIssue("demo-1", "ops").change()) == "Clone DEMO-1 into OPS"
    assert str(DeleteIssue("demo-1", subtasks=True).change()) == (
        "Permanently delete DEMO-1 with their subtasks"
    )
    assert str(ArchiveIssue("DEMO-1", archive=False).change()) == "Unarchive DEMO-1"
    assert ArchiveIssue("DEMO-1", archive=False).previews() is None


def test_many_creations_merge_into_a_count():
    rows = [
        CreateIssue({"summary": "a", "project": {"key": "DEMO"}}, ref="#1"),
        CreateIssue({"summary": "b", "project": {"key": "DEMO"}}, ref="#2"),
    ]
    merged = change_of(rows)
    assert merged is not None
    assert str(merged) == "Create 2 issues"
    assert merged.adds
    deletes = change_of([DeleteIssue("DEMO-1"), DeleteIssue("DEMO-2")])
    assert deletes is not None
    assert deletes.destructive


def test_one_addition_goes_ahead_without_asking():
    confirm = Confirm(None, lambda: False)
    assert not confirm.will_ask(Change("Create", ("#1",), adds=True))
    assert confirm.will_ask(Change("Create", ("#1", "#2"), adds=True))
    assert confirm.will_ask(Change("Delete", ("DEMO-1",)))
    asyncio.run(confirm.approve(Change("Clone", ("DEMO-1",), adds=True)))  # no way to ask: fine


# ── handlers, over stub ports ────────────────────────────────────────────────


class StubSite:
    """`IssueStore`, `Destination`, `IssueLinks`, `IssueEditor` and `IssueReader` in memory."""

    def __init__(self, *, elsewhere: bool = False) -> None:
        self.done: list[tuple] = []
        self.elsewhere = elsewhere
        self.url = "https://other.example"

    def values(self, key: str, field_ids: tuple[str, ...]) -> dict[str, Any]:
        return {f: ORIGINAL.get(f) for f in field_ids} | {"status": {"name": "To Do"}}

    def create(self, fields: Any, update: Any) -> str:
        self.done.append(("create", fields["project"]["key"], fields["summary"]))
        return "OPS-9"

    def delete(self, key: str, *, subtasks: bool = False) -> None:
        self.done.append(("delete", key, subtasks))

    def archive(self, key: str, *, archive: bool = True) -> None:
        self.done.append(("archive", key, archive))

    def web_link(self, key: str, url: str, title: str) -> None:
        self.done.append(("web link", key, url, title))

    def link_types(self) -> tuple[LinkType, ...]:
        return (LinkType("Cloners", "clones", "is cloned by"),)

    def link(self, link: IssueLink, comment: Any = None) -> None:
        self.done.append(("link", link.type.name, link.outward, link.inward))

    def browse_url(self, key: str) -> str:
        return f"https://here.example/browse/{key}"


def send(package: Any, stub: StubSite, command: Any) -> Any:
    """Send `command` through a mediator that knows only `package`, every port being `stub`."""

    class Resolver:
        def resolve(self, cls: Any, /) -> Any:
            assert cls in (IssueStore, Destination, IssueLinks, IssueEditor, IssueReader)
            return stub

    mediator = Mediator(resolver=Resolver())
    mediator.scan(package)
    return asyncio.run(mediator.send(command))


def test_create_names_the_new_issue():
    stub = StubSite()
    changed = send(create_issue, stub, CreateIssue.of("OPS", "Task", "New"))
    assert (changed.key, changed.before) == ("OPS-9", {})
    assert changed.after == {"created": "OPS-9", "project": "OPS", "summary": "New"}


def test_clone_links_the_copy_here_and_links_back_from_elsewhere():
    here = StubSite()
    changed = send(clone_issue, here, CloneIssue("demo-1", "ops"))
    assert here.done == [("create", "OPS", "Login fails"), ("link", "Cloners", "OPS-9", "DEMO-1")]
    assert changed.after == {"created": "OPS-9", "clone_of": "DEMO-1"}
    there = StubSite(elsewhere=True)
    changed = send(clone_issue, there, CloneIssue("DEMO-1", "ops"))
    assert there.done[-1] == (
        "web link", "OPS-9", "https://here.example/browse/DEMO-1", "Cloned from DEMO-1",
    )  # fmt: skip
    assert changed.after["site"] == "https://other.example"
    unlinked = StubSite()
    send(clone_issue, unlinked, CloneIssue("DEMO-1", link=False))
    assert [d[0] for d in unlinked.done] == ["create"]


def test_delete_notes_what_the_issue_was():
    stub = StubSite()
    changed = send(delete_issue, stub, DeleteIssue("demo-1", subtasks=True))
    assert stub.done == [("delete", "DEMO-1", True)]
    assert changed.before["summary"] == "Login fails"
    assert changed.after == {"deleted": True}


def test_archive_and_restore():
    stub = StubSite()
    changed = send(archive_issue, stub, ArchiveIssue("demo-1", archive=False))
    assert stub.done == [("archive", "DEMO-1", False)]
    assert (changed.before, changed.after) == ({"archived": True}, {"archived": False})


# ── reading many issues to create ────────────────────────────────────────────


def test_rows_come_as_json_a_list_or_json_lines():
    assert parse_rows('{"summary": "a"}') == [{"summary": "a"}]
    assert parse_rows('{"issues": [{"summary": "a"}]}') == [{"summary": "a"}]
    assert parse_rows('{"summary": "a"}\n\n{"summary": "b"}\n') == [
        {"summary": "a"}, {"summary": "b"},
    ]  # fmt: skip
    assert parse_rows("  ") == []
    with pytest.raises(ResolveError, match="line 2 is not JSON"):
        parse_rows('{"summary": "a"}\n{"summary": \n')
    with pytest.raises(ResolveError, match="not JSON or JSON lines"):
        parse_rows("summary: a")
    with pytest.raises(ResolveError, match="issue 1 is not a JSON object"):
        parse_rows('["a"]')


# ── the CLI ──────────────────────────────────────────────────────────────────


def audit_lines() -> list[dict]:
    return [json.loads(line) for line in default_path().read_text().splitlines()]


def test_cli_creates_from_json_lines_on_stdin_in_order(site):
    piped = '{"summary": "First"}\n{"summary": "Second", "type": "Bug"}\n'
    result, out = run_cli("issue", "create", "--from-json", "-", "-p", "DEMO", "-y", input=piped)
    assert result.exit_code == 0, out
    assert "#1 created as DEMO-4" in out
    assert "#2 created as DEMO-5" in out
    assert site.issues["DEMO-5"]["fields"]["issuetype"]["name"] == "Bug"
    (record,) = audit_lines()
    assert record["command"] == "CreateIssue"
    assert record["keys"] == ["DEMO-4", "DEMO-5"]


def test_cli_create_many_previews_then_asks(site, monkeypatch, tmp_path):
    monkeypatch.setattr(common, "interactive", lambda: True)
    asked: list[str] = []
    monkeypatch.setattr(terminal, "ask", lambda q: asked.append(q) or False)
    path = tmp_path / "new.json"
    path.write_text(json.dumps([{"summary": "Alpha"}, {"summary": "Beta", "project": "OPS"}]))
    result, out = run_cli("issue", "create", "--from-json", str(path), "-p", "DEMO")
    assert result.exit_code == 2
    assert asked == ["Create 2 issues?"]
    for text in ("#1", "Alpha", "Task in DEMO", "Beta", "Task in OPS"):
        assert text in out, text
    assert site.writes() == []


def test_cli_one_create_or_clone_does_not_ask(site, monkeypatch):
    monkeypatch.setattr(common, "interactive", lambda: True)
    monkeypatch.setattr(terminal, "ask", lambda q: pytest.fail(f"asked {q}"))
    result, out = run_cli("issue", "create", "-p", "DEMO", "-s", "Quiet")
    assert result.exit_code == 0, out
    assert "Created DEMO-4" in out
    result, out = run_cli("issue", "clone", "DEMO-1")
    assert result.exit_code == 0, out
    assert "DEMO-1 cloned as DEMO-5" in out


def test_cli_delete_many_needs_the_count_typed(site, monkeypatch):
    monkeypatch.setattr(common, "interactive", lambda: True)
    asked: list[str] = []

    def answer(prompt: str) -> str:
        asked.append(prompt)
        return typed

    monkeypatch.setattr(terminal, "answer", answer)
    typed = "y"
    result, out = run_cli("issue", "delete", "DEMO-1", "DEMO-2")
    assert result.exit_code == 2
    assert asked == [
        "Permanently delete 2 issues (DEMO-1, DEMO-2)? This can't be undone. Type 2 to agree"
    ]
    assert "Login fails on Safari" in out  # the preview names what goes
    assert "deleted" in out
    assert site.writes() == []
    typed = "2"
    result, out = run_cli("issue", "delete", "DEMO-1", "DEMO-2")
    assert result.exit_code == 0, out
    assert not {"DEMO-1", "DEMO-2"} & set(site.issues)
    (record,) = audit_lines()
    assert record["command"] == "DeleteIssue"
    assert {c["before"]["summary"] for c in record["changes"]} >= {"Login fails on Safari"}


def test_cli_delete_one_asks_yes_or_no(site, monkeypatch):
    monkeypatch.setattr(common, "interactive", lambda: True)
    asked: list[str] = []
    monkeypatch.setattr(terminal, "ask", lambda q: asked.append(q) or True)
    result, out = run_cli("issue", "delete", "DEMO-3")
    assert result.exit_code == 0, out
    assert asked == ["Permanently delete DEMO-3?"]
    assert "DEMO-3" not in site.issues


def test_cli_lifecycle_from_a_pipe(site):
    result, out = run_cli("issue", "archive", "-", "-y", input="DEMO-1\nDEMO-2\n")
    assert result.exit_code == 0, out
    assert "2 of 2 archived." in out
    result, out = run_cli("issue", "unarchive", "-", "-y", input="DEMO-1\n")
    assert result.exit_code == 0, out
    assert not site.issues["DEMO-1"]["archived"]
    result, out = run_cli("issue", "clone", "-", "-y", "--prefix", "Copy: ", input="DEMO-3\n")
    assert result.exit_code == 0, out
    assert site.issues["DEMO-4"]["fields"]["summary"].startswith("Copy: ")


@pytest.mark.parametrize("command", ["delete", "archive", "clone"])
def test_cli_nothing_picked_does_nothing(site, command):
    result, out = run_cli("issue", command, "-", "-y", input="")
    assert result.exit_code == 0, out
    assert "No issues match" in out
    assert site.writes() == []


def test_cli_dry_run_creates_nothing_and_keeps_nothing(site, tmp_path):
    path = tmp_path / "new.json"
    path.write_text(json.dumps([{"summary": "a"}, {"summary": "b"}]))
    result, out = run_cli("issue", "create", "--from-json", str(path), "-p", "DEMO", "--dry-run")
    assert result.exit_code == 0, out
    assert "#2 would be created" in out
    assert site.writes() == []
    assert not default_path().exists()


def test_answer_reads_a_line_on_the_terminal(monkeypatch):
    import io
    import sys

    from tests.test_pipes import FakeTty

    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    tty = FakeTty(" 3 \n")
    monkeypatch.setattr(terminal, "open_tty", tty)
    assert terminal.answer("Type 3 to agree") == "3"
    assert tty.asked == "Type 3 to agree: "
    monkeypatch.setattr(terminal, "open_tty", lambda: None)
    assert terminal.answer("Type 3 to agree") == ""
