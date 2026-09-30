"""The `transition_issue` use case: the domain, the handler, confirmation, the event and audit."""

from __future__ import annotations

import asyncio
import json
import os
import stat
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from mediary import Mediator

from acli_py.application.changes import AuditRecord, Change, Changed, Declined
from acli_py.application.commands import transition_issue as transition_package
from acli_py.application.commands.transition_issue.command import TransitionIssue
from acli_py.application.messages import CountIssues
from acli_py.application.ports import AuditLog, Workflow
from acli_py.application.site import Site
from acli_py.bootstrap import build_bus
from acli_py.domain.issue import Status, StatusCategory
from acli_py.domain.workflow import NoSuchTransitionError, Transition, pick
from acli_py.infrastructure.audit import AuditFile
from acli_py.infrastructure.jira.client import JiraClient
from acli_py.presentation.cli import common
from tests import fake_jira

if TYPE_CHECKING:
    from acli_py.application.events.issue_changed.event import IssueChanged

START = Transition("11", "Start work", Status("In Progress", StatusCategory.IN_PROGRESS))
FINISH = Transition("31", "Finish", Status("Done", StatusCategory.DONE))


# ── domain ───────────────────────────────────────────────────────────────────


def test_transitions_read_jira_json():
    data = {"id": "31", "name": "Finish", "to": {"name": "Done", "statusCategory": {"key": "done"}}}
    assert Transition.from_jira(data) == FINISH
    assert Transition.from_jira({"name": "no id"}) is None
    assert Transition("5", "Reopen").target == "Reopen"


def test_pick_by_id_then_status_then_name():
    assert pick([START, FINISH], "31", "DEMO-1") is FINISH
    assert pick([START, FINISH], " done ", "DEMO-1") is FINISH
    assert pick([START, FINISH], "start WORK", "DEMO-1") is START
    with pytest.raises(NoSuchTransitionError, match=r"Available: Start work → In Progress, Fin"):
        pick([START, FINISH], "Nowhere", "DEMO-1")
    with pytest.raises(NoSuchTransitionError, match="Available: none"):
        pick([], "Done", "DEMO-1")


def test_changes_read_as_sentences():
    assert str(Change("Move", ("DEMO-1",), "to Done")) == "Move DEMO-1 to Done"
    many = Change("Move", tuple(f"DEMO-{n}" for n in range(1, 8)), "to Done")
    assert str(many) == "Move 7 issues (DEMO-1, DEMO-2, DEMO-3, DEMO-4, DEMO-5…) to Done"
    assert many.covers(Change("Move", ("DEMO-3",), "to Done"))
    assert not many.covers(Change("Move", ("DEMO-3",), "to To Do"))
    assert not many.covers(Change("Move", ("OPS-1",), "to Done"))


# ── handler ──────────────────────────────────────────────────────────────────


class StubWorkflow:
    """A `Workflow` in memory, recording the transitions applied."""

    def __init__(self) -> None:
        self.applied: list[tuple[str, str, dict, str]] = []

    def status(self, key: str) -> Status | None:
        return Status("To Do", StatusCategory.TO_DO)

    def transitions(self, key: str) -> list[Transition]:
        return [START, FINISH]

    def transition(self, key: str, transition_id: str, fields: Any, comment: str) -> None:
        self.applied.append((key, transition_id, dict(fields), comment))


def test_handler_moves_through_the_port():
    workflow = StubWorkflow()

    class Resolver:
        def resolve(self, cls: Any, /) -> Any:
            assert cls is Workflow
            return workflow

    mediator = Mediator(resolver=Resolver())
    mediator.scan(transition_package)
    command = TransitionIssue(" demo-1 ", "done", "Shipped", {"resolution": {"name": "Done"}})
    changed = asyncio.run(mediator.send(command))
    assert changed == Changed("DEMO-1", {"status": "To Do"}, {"status": "Done"})
    assert workflow.applied == [("DEMO-1", "31", {"resolution": {"name": "Done"}}, "Shipped")]
    assert command.change() == Change("Move", ("DEMO-1",), "to done")


# ── confirmation ─────────────────────────────────────────────────────────────


class Answers:
    """A `Confirmer` answering from a script, recording what it was asked."""

    def __init__(self, *answers: bool) -> None:
        self.answers = list(answers)
        self.asked: list[str] = []

    async def confirm(self, change: Change) -> bool:
        self.asked.append(str(change))
        return self.answers.pop(0)


class Kept:
    """An `AuditLog` in memory."""

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def record(self, entry: AuditRecord) -> None:
        self.records.append(entry)


def fake_bus(url: str, *, dry_run: bool = False, **options: Any):
    client = JiraClient(url, fake_jira.EMAIL, fake_jira.TOKEN, dry_run=dry_run, retries=0)
    return build_bus(Site(client, url), **options)


def test_confirm_accepted_runs_the_command(site, fake):
    answers, audit = Answers(True), Kept()
    bus = fake_bus(fake[1], confirmer=answers, audit=audit)
    heard: list[IssueChanged] = []
    bus.listeners.append(heard.append)
    changed = asyncio.run(bus.send(TransitionIssue("DEMO-1", "Done")))
    assert answers.asked == ["Move DEMO-1 to Done"]
    assert changed.after == {"status": "Done"}
    assert site.issues["DEMO-1"]["fields"]["status"]["name"] == "Done"
    assert [(h.key, h.before, h.after) for h in heard] == [
        ("DEMO-1", {"status": "To Do"}, {"status": "Done"})
    ]
    (record,) = audit.records
    assert (record.command, record.keys, record.after) == (
        "TransitionIssue",
        ("DEMO-1",),
        {"status": "Done"},
    )


def test_confirm_declined_changes_nothing(site, fake):
    answers, audit = Answers(False), Kept()
    bus = fake_bus(fake[1], confirmer=answers, audit=audit)
    with pytest.raises(Declined, match="Cancelled"):
        asyncio.run(bus.send(TransitionIssue("DEMO-1", "Done")))
    assert site.writes() == []
    assert audit.records == []


def test_yes_and_dry_runs_never_ask(site, fake):
    answers = Answers()
    bus = fake_bus(fake[1], confirmer=answers, assume_yes=True, audit=Kept())
    asyncio.run(bus.send(TransitionIssue("DEMO-1", "In Progress")))
    audit = Kept()
    dry = fake_bus(fake[1], dry_run=True, confirmer=answers, audit=audit)
    asyncio.run(dry.send(TransitionIssue("DEMO-2", "Done")))
    assert answers.asked == []
    assert site.issues["DEMO-2"]["fields"]["status"]["name"] == "To Do"
    assert audit.records == []  # a dry run changed nothing


def test_no_way_to_ask_declines(site, fake):
    bus = fake_bus(fake[1], audit=Kept())
    with pytest.raises(Declined, match="no way to ask"):
        asyncio.run(bus.send(TransitionIssue("DEMO-1", "Done")))
    assert site.writes() == []


def test_a_batch_asks_once_and_only_for_what_it_covers(site, fake):
    answers = Answers(True, True)
    bus = fake_bus(fake[1], confirmer=answers, audit=Kept())

    async def scenario():
        async with bus.confirm.batch(Change("Move", ("DEMO-1", "DEMO-2"), "to Done")):
            await bus.send(TransitionIssue("DEMO-1", "Done"))
            await bus.send(TransitionIssue("demo-2", "Done"))
            await bus.send(TransitionIssue("DEMO-3", "Done"))  # not covered: asked
            await bus.send(CountIssues("project = DEMO"))  # reads are never asked about
        assert bus.confirm.approved == []
        await bus.confirm.approve(Change("Move", ("DEMO-1",), "to To Do"), yes=True)

    asyncio.run(scenario())
    assert answers.asked == ["Move 2 issues (DEMO-1, DEMO-2) to Done", "Move DEMO-3 to Done"]


# ── the terminal and the audit file ──────────────────────────────────────────


def test_terminal_asks_only_on_a_terminal(monkeypatch):
    change = Change("Move", ("DEMO-1",), "to Done")
    confirmer = common.TerminalConfirmer()
    monkeypatch.setattr(common.sys.stdin, "isatty", lambda: False, raising=False)
    with pytest.raises(Declined, match=r"Move DEMO-1 to Done\? Refusing without --yes"):
        asyncio.run(confirmer.confirm(change))
    asked: list[str] = []
    monkeypatch.setattr(common.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(
        common.typer, "confirm", lambda question, **_: asked.append(question) or True
    )
    assert asyncio.run(confirmer.confirm(change))
    assert asked == ["Move DEMO-1 to Done?"]


def test_audit_file_appends_private_json_lines(tmp_path):
    log: AuditLog = AuditFile(tmp_path / "logs" / "audit.jsonl")
    at = datetime(2026, 9, 30, 12, tzinfo=UTC)
    for key in ("DEMO-1", "DEMO-2"):
        log.record(AuditRecord("TransitionIssue", (key,), {"status": "To Do"}, {"when": at}, at))
    lines = (tmp_path / "logs" / "audit.jsonl").read_text().splitlines()
    assert [json.loads(line)["keys"] for line in lines] == [["DEMO-1"], ["DEMO-2"]]
    assert json.loads(lines[0]) == {
        "at": "2026-09-30T12:00:00+00:00", "command": "TransitionIssue", "keys": ["DEMO-1"],
        "before": {"status": "To Do"}, "after": {"when": "2026-09-30 12:00:00+00:00"},
    }  # fmt: skip
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / "logs" / "audit.jsonl").stat().st_mode) == 0o600


def test_audit_file_that_cannot_be_written_is_skipped(tmp_path):
    (tmp_path / "taken").write_text("a file, not a directory")
    at = datetime.now(UTC)
    AuditFile(tmp_path / "taken" / "audit.jsonl").record(AuditRecord("X", ("K-1",), {}, {}, at))
