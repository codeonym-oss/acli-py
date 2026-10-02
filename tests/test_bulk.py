"""The bulk engine: preview, one question, bounded concurrency, failures, the cap and audit."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import pytest

from acli_py.application.audit import AuditTrail
from acli_py.application.behaviors import Confirm
from acli_py.application.bulk import SAFETY_CAP, Bulk, TooManyError, change_of
from acli_py.application.changes import Change, Changed, Declined, PreviewRow
from acli_py.application.commands.transition_issue.command import TransitionIssue
from acli_py.application.site import Site
from acli_py.bootstrap import build_bus
from acli_py.infrastructure.audit import AuditMemory
from acli_py.infrastructure.jira.client import JiraClient
from acli_py.presentation import terminal
from acli_py.presentation.cli import common
from tests import fake_jira
from tests.conftest import run_cli


class Answers:
    """A `Confirmer` answering from a script, recording what it was shown."""

    def __init__(self, *answers: bool) -> None:
        self.answers = list(answers)
        self.asked: list[Change] = []

    async def confirm(self, change: Change) -> bool:
        self.asked.append(change)
        return self.answers.pop(0)


Kept = AuditMemory  # an `AuditLog` in memory


def fake_bus(url: str, **options: Any):
    client = JiraClient(url, fake_jira.EMAIL, fake_jira.TOKEN, retries=0)
    return build_bus(Site(client, url), **options)


# ── the engine, on the fake site ─────────────────────────────────────────────


def test_asks_once_with_a_preview_then_keeps_one_audit_record(site, fake):
    answers, audit = Answers(True), Kept()
    bus = fake_bus(fake[1], confirmer=answers, audit=audit)
    seen: list[str] = []
    commands = [TransitionIssue(k, "Done") for k in ("DEMO-1", "DEMO-2", "DEMO-3")]
    report = asyncio.run(bus.bulk.run(commands, on_outcome=lambda o: seen.append(o.key)))
    (asked,) = answers.asked
    assert str(asked) == "Move 3 issues (DEMO-1, DEMO-2, DEMO-3) to Done"
    assert asked.preview[0] == PreviewRow("DEMO-1", "Login fails on Safari", "To Do", "Done")
    assert [row.key for row in asked.preview] == ["DEMO-1", "DEMO-2", "DEMO-3"]
    assert report.exit_code == 0
    assert sorted(seen) == ["DEMO-1", "DEMO-2", "DEMO-3"]
    assert all(site.issues[k]["fields"]["status"]["name"] == "Done" for k in seen)
    (record,) = audit.records  # one record for the run, not one per issue
    assert record.command == "TransitionIssue"
    assert sorted(record.keys) == ["DEMO-1", "DEMO-2", "DEMO-3"]
    assert record.failed == {}


def test_declined_runs_nothing(site, fake):
    audit = Kept()
    bus = fake_bus(fake[1], confirmer=Answers(False), audit=audit)
    with pytest.raises(Declined):
        asyncio.run(bus.bulk.run([TransitionIssue(k, "Done") for k in ("DEMO-1", "DEMO-2")]))
    assert site.writes() == []
    assert audit.records == []
    assert bus.confirm.approved == []


def test_failures_stop_the_run_unless_told_to_keep_going(site, fake):
    commands = [TransitionIssue(k, "Done") for k in ("DEMO-404", "DEMO-1", "DEMO-2")]
    audit = Kept()
    bus = fake_bus(fake[1], assume_yes=True, audit=audit)
    report = asyncio.run(bus.bulk.run(commands, concurrency=1))
    assert [o.key for o in report.failed] == ["DEMO-404"]
    assert (report.not_tried, report.exit_code) == (2, 1)
    assert site.writes() == []
    (record,) = audit.records  # a failure is kept too
    assert list(record.failed) == ["DEMO-404"]
    assert record.changes == ()

    report = asyncio.run(bus.bulk.run(commands, concurrency=1, keep_going=True))
    assert (len(report.succeeded), len(report.failed), report.not_tried) == (2, 1, 0)
    assert report.exit_code == 1
    assert [len(r.changes) for r in audit.records] == [0, 2]


def test_a_dry_run_is_not_audited(site, fake):
    client = JiraClient(fake[1], fake_jira.EMAIL, fake_jira.TOKEN, dry_run=True, retries=0)
    audit = Kept()
    bus = build_bus(Site(client, fake[1]), audit=audit)  # no confirmer: dry runs never ask
    report = asyncio.run(bus.bulk.run([TransitionIssue("DEMO-1", "Done")]))
    assert report.exit_code == 0
    assert audit.records == []


# ── the engine, with a stub bus ──────────────────────────────────────────────


@dataclass(frozen=True)
class Touch:
    """A `Write` command that takes a little while."""

    key: str

    def change(self) -> Change:
        return Change("Touch", (self.key,))


@dataclass(frozen=True)
class Untold:
    """A command that doesn't say what it changes."""

    key: str


def stub_bulk(send: Any, *, audit: Kept | None = None) -> Bulk:
    confirm = Confirm(None, lambda: False, assume_yes=True)
    return Bulk(send, confirm, AuditTrail(audit or Kept()), lambda: False)


def test_concurrency_is_bounded():
    running, most = 0, 0

    async def send(command: Touch) -> str:
        nonlocal running, most
        running += 1
        most = max(most, running)
        await asyncio.sleep(0.005)
        running -= 1
        return command.key

    commands = [Touch(f"K-{n}") for n in range(12)]
    report = asyncio.run(stub_bulk(send).run(commands, concurrency=3))
    assert (most, len(report.succeeded)) == (3, 12)
    asyncio.run(stub_bulk(send).run(commands, concurrency=99))
    assert most == 12  # capped at MAX_CONCURRENCY, which is more than 12


def test_the_safety_cap_needs_force():
    async def send(command: Touch) -> None:
        return None

    commands = [Touch(f"K-{n}") for n in range(SAFETY_CAP + 1)]
    with pytest.raises(TooManyError, match=f"{SAFETY_CAP + 1} issues is over the safety cap"):
        asyncio.run(stub_bulk(send).run(commands))
    assert asyncio.run(stub_bulk(send).run(commands, force=True)).exit_code == 0


def test_change_of_merges_or_gives_up():
    same = [TransitionIssue("DEMO-1", "Done"), TransitionIssue("demo-2", "Done")]
    assert change_of(same) == Change("Move", ("DEMO-1", "DEMO-2"), "to Done")
    mixed = [TransitionIssue("DEMO-1", "Done"), TransitionIssue("DEMO-2", "To Do")]
    assert change_of(mixed) == Change("Move", ("DEMO-1", "DEMO-2"))
    assert change_of([Untold("DEMO-1")]) is None
    assert change_of([]) is None


def test_commands_that_do_not_say_run_without_a_batch():
    sent: list[Any] = []

    async def send(command: Any) -> None:
        sent.append(command)

    commands = [Untold("DEMO-1"), Untold("DEMO-2")]
    report = asyncio.run(stub_bulk(send).run(commands))
    assert (report.exit_code, sent) == (0, commands)


def test_preview_marks_issues_it_cannot_find(site, fake):
    bus = fake_bus(fake[1], assume_yes=True, audit=Kept())
    rows = asyncio.run(bus.bulk.preview([TransitionIssue("DEMO-404", "Done")]))
    assert rows == (PreviewRow("DEMO-404", "", "?", "Done"),)
    assert asyncio.run(bus.bulk.preview([Touch("K-1")])) == ()


# ── the CLI ──────────────────────────────────────────────────────────────────


def test_cli_moves_a_query_with_a_summary(site):
    result, out = run_cli("issue", "transition", "--jql", "p:DEMO", "--to", "Done", "-y")
    assert result.exit_code == 0, out
    assert "3 of 3 moved." in out
    assert all(i["fields"]["status"]["name"] == "Done" for i in site.issues.values()
               if i["key"].startswith("DEMO"))  # fmt: skip


def test_cli_exit_codes_and_continue_on_error(site):
    result, out = run_cli(
        "issue", "transition", "DEMO-404", "DEMO-1", "--to", "Done", "-y", "-c", "1"
    )
    assert result.exit_code == 1
    assert "0 of 2 moved, 1 failed, 1 not tried." in out
    result, out = run_cli(
        "issue", "transition", "DEMO-404", "DEMO-1", "--to", "Done", "-y", "--continue-on-error"
    )
    assert result.exit_code == 1
    assert "1 of 2 moved, 1 failed." in out
    assert site.issues["DEMO-1"]["fields"]["status"]["name"] == "Done"


def test_cli_limit_and_json(site):
    result, out = run_cli(
        "issue", "transition", "--jql", "project = DEMO ORDER BY key", "--to", "Done",
        "--limit", "2", "-y", "--json",
    )  # fmt: skip
    assert result.exit_code == 0, out
    data = json.loads(out)
    assert sorted(d["item"] for d in data) == ["DEMO-1", "DEMO-2"]
    assert data[0]["result"]["after"] == {"status": "Done"}


def test_cli_over_the_cap_needs_force(site, monkeypatch):
    monkeypatch.setattr(common, "SAFETY_CAP", 1)
    monkeypatch.setattr("acli_py.application.bulk.SAFETY_CAP", 1)
    result, out = run_cli("issue", "transition", "DEMO-1", "DEMO-2", "--to", "Done", "-y")
    assert result.exit_code == 2
    assert "2 issues is over the safety cap of 1. Narrow it down, or pass --force" in out
    assert site.writes() == []
    result, out = run_cli(
        "issue", "transition", "DEMO-1", "DEMO-2", "--to", "Done", "-y", "--force"
    )
    assert result.exit_code == 0, out


def test_cli_shows_the_preview_then_asks(site, monkeypatch):
    monkeypatch.setattr(common, "interactive", lambda: True)
    asked: list[str] = []
    monkeypatch.setattr(terminal, "ask", lambda q: asked.append(q) or False)
    result, out = run_cli("issue", "transition", "DEMO-1", "DEMO-3", "--to", "To Do")
    assert result.exit_code == 2  # declined: nothing ran
    assert asked == ["Move 2 issues (DEMO-1, DEMO-3) to To Do?"]
    for text in ("Issue", "Now", "After", "Login fails on Safari", "Speed up search"):
        assert text in out, text
    assert site.writes() == []


def test_changed_results_serialise():
    assert common.plain(type("O", (), {"result": Changed("K-1", {}, {"s": 1})})()) == {
        "key": "K-1", "before": {}, "after": {"s": 1},
    }  # fmt: skip
