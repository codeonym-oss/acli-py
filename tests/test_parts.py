"""The parts of an issue as use cases: the link rule, the commands' changes, bulk runs, audit."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from acli_py.application.bulk import change_of
from acli_py.application.commands.attach_file.command import AttachFile
from acli_py.application.commands.comment_on_issue.command import CommentOnIssue
from acli_py.application.commands.delete_comment.command import DeleteComment
from acli_py.application.commands.link_issues.command import LinkIssues
from acli_py.application.commands.log_work.command import LogWork
from acli_py.application.commands.unlink_issues.command import UnlinkIssues
from acli_py.application.queries.download_attachment.query import DownloadAttachment
from acli_py.application.site import Site
from acli_py.bootstrap import build_bus
from acli_py.domain.adf import to_text
from acli_py.domain.links import IssueLink, LinkDirection, LinkType, UnknownLinkTypeError
from acli_py.infrastructure.audit import AuditMemory
from acli_py.infrastructure.jira.client import JiraClient
from acli_py.presentation import terminal
from acli_py.presentation.cli import common
from tests import fake_jira
from tests.conftest import run_cli

BLOCKS = LinkType("Blocks", "blocks", "is blocked by", "1")
DUPLICATE = LinkType("Duplicate", "duplicates", "is duplicated by", "2")
RULE = LinkDirection([BLOCKS, DUPLICATE])


def ok(*args: str, input: str | None = None) -> str:
    result, out = run_cli(*args, input=input)
    assert result.exit_code == 0, out
    return out


# ── the link direction rule ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("source", "kind", "target", "outward", "inward"),
    [
        ("DEMO-1", "blocks", "DEMO-2", "DEMO-1", "DEMO-2"),  # the outward phrase
        ("DEMO-2", "is blocked by", "DEMO-1", "DEMO-1", "DEMO-2"),  # the inward one: swapped
        ("demo-1", "Blocks", "demo-2", "DEMO-1", "DEMO-2"),  # the type's name reads outward
        (" DEMO-5 ", "IS DUPLICATED BY", "OPS-9", "OPS-9", "DEMO-5"),
    ],
)
def test_a_sentence_becomes_the_link_jira_stores(source, kind, target, outward, inward):
    link = RULE.link(source, kind, target)
    assert (link.outward, link.inward) == (outward, inward)
    assert link.to_jira() == {
        "type": {"name": link.type.name},
        "outwardIssue": {"key": outward},
        "inwardIssue": {"key": inward},
    }
    assert str(link) == f"{outward} {link.type.outward} {inward}"


def test_an_unknown_link_type_lists_the_ones_there_are():
    with pytest.raises(UnknownLinkTypeError, match=r"no link type 'fixes'.*Blocks \(blocks"):
        RULE.link("DEMO-1", "fixes", "DEMO-2")
    assert RULE.named("duplicate") is DUPLICATE
    assert RULE.named("Cloners") is None


def test_links_read_back_from_jira():
    data = {"id": "7", "type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
            "outwardIssue": {"key": "A-1"}, "inwardIssue": {"key": "A-2"}}  # fmt: skip
    assert IssueLink.from_jira(data) == IssueLink(LinkType("Blocks", "blocks", "is blocked by"),
                                                  "A-1", "A-2")  # fmt: skip
    assert LinkType.from_jira({"name": "Odd"}) == LinkType("Odd", "Odd", "Odd")


# ── what the commands say they change ────────────────────────────────────────


def test_changes_read_as_sentences():
    assert str(CommentOnIssue("demo-1", "hi").change()) == "Comment on DEMO-1"
    assert str(DeleteComment("DEMO-1", "9").change()) == "Delete comment 9 on DEMO-1"
    assert str(UnlinkIssues("7").change()) == "Delete link 7"
    assert str(LinkIssues("a-1", "blocks", "a-2").change()) == "Add link A-1 blocks A-2"
    assert str(LogWork("DEMO-1", "1h 30m").change()) == "Log 1h 30m on DEMO-1"
    assert str(AttachFile("DEMO-1", Path("x/r.txt")).change()) == ("Attach r.txt to DEMO-1")


def test_many_parts_merge_into_one_question_that_counts_them():
    merged = change_of([DeleteComment("DEMO-1", "8"), DeleteComment("DEMO-1", "9")])
    assert merged is not None
    assert str(merged) == "Delete 2 comments"
    assert merged.destructive
    assert merged.keys == ("8", "9")
    merged = change_of([CommentOnIssue("DEMO-1", "x"), CommentOnIssue("DEMO-2", "x")])
    assert merged is not None
    assert str(merged) == "Comment on 2 issues (DEMO-1, DEMO-2)"


def test_log_work_refuses_what_is_not_a_duration():
    with pytest.raises(ValueError, match="not a duration"):
        LogWork("DEMO-1", "a while")


# ── bulk runs from the CLI ───────────────────────────────────────────────────


def test_comment_on_keys_piped_in(site):
    out = ok("issue", "comment", "add", "-", "-b", "Shipped", "-y", input="DEMO-1\nOPS-1\n")
    assert "2 of 2 commented" in out
    assert to_text(site.issues["OPS-1"]["comments"][-1]["body"]) == "Shipped"


def test_link_every_issue_a_query_finds(site):
    out = ok("issue", "link", "add", "--jql", "project = DEMO", "relates to", "OPS-1", "-y")
    assert "3 of 3 linked" in out
    assert sum(link["inward"] == "OPS-1" for link in site.links.values()) == 3
    assert ok("issue", "link", "list", "DEMO-1", "--output", "keys").split() == ["DEMO-3", "OPS-1"]


def test_log_work_on_many_issues(site):
    out = ok("issue", "worklog", "add", "DEMO-1", "DEMO-2", "-t", "15m", "-m", "Standup", "-y")
    assert "2 of 2 logged 15m" in out
    assert site.issues["DEMO-2"]["worklogs"][-1]["timeSpent"] == "15m"
    result, out = run_cli("issue", "worklog", "add", "DEMO-1")
    assert result.exit_code == 1
    assert "How long?" in out


def test_deleting_several_parts_asks_to_type_the_count(site, monkeypatch):
    ok("issue", "comment", "add", "DEMO-2", "-b", "one")
    ok("issue", "comment", "add", "DEMO-2", "-b", "two")
    ids = [c["id"] for c in site.issues["DEMO-2"]["comments"]]
    monkeypatch.setattr(common, "interactive", lambda: True)
    asked: list[str] = []
    monkeypatch.setattr(terminal, "answer", lambda q: asked.append(q) or "1")
    result, _ = run_cli("issue", "comment", "delete", "DEMO-2", *ids)
    assert result.exit_code == 2  # the wrong count: nothing deleted
    assert asked == ["Delete 2 comments? This can't be undone. Type 2 to agree"]
    assert len(site.issues["DEMO-2"]["comments"]) == 2


def test_list_json_shapes(site):
    data = json.loads(ok("issue", "worklog", "list", "DEMO-3", "--json"))
    assert data[0]["timeSpent"] == "2h"
    assert data[0]["author"]["name"] == "Bob Jensen"
    data = json.loads(ok("issue", "watcher", "list", "DEMO-2", "--json"))
    assert all({"accountId", "name", "active"} <= set(w) for w in data)
    data = json.loads(ok("issue", "link", "types", "--json"))
    assert {"id", "name", "outward", "inward"} == set(data[0])


# ── on the bus: audit and downloads ──────────────────────────────────────────


Kept = AuditMemory  # an `AuditLog` in memory


def fake_bus(url: str, audit: Kept):
    client = JiraClient(url, fake_jira.EMAIL, fake_jira.TOKEN, retries=0)
    return build_bus(Site(client, url), assume_yes=True, audit=audit)


def test_deletions_keep_what_was_deleted(site, fake):
    audit = Kept()
    bus = fake_bus(fake[1], audit)
    comment = site.issues["DEMO-1"]["comments"][0]["id"]
    link = next(iter(site.links))

    async def scenario() -> None:
        await bus.send(DeleteComment("DEMO-1", comment))
        await bus.send(UnlinkIssues(link))

    asyncio.run(scenario())
    first, second = (r.changes[0] for r in audit.records)
    assert first.before["body"] == "Seen on **Safari 18** too."
    assert first.before["author"] == fake_jira.BOB["accountId"]
    assert second.key == "DEMO-1"
    assert second.before["link"] == "DEMO-1 blocks DEMO-3"


def test_downloads_are_never_answered_from_the_cache(site, fake, tmp_path):
    bus = fake_bus(fake[1], Kept())
    query = DownloadAttachment("20008", tmp_path)
    saved = asyncio.run(bus.send(query))
    assert (saved.path.name, saved.size) == ("trace.log", 3)
    saved.path.unlink()
    asyncio.run(bus.send(query))
    assert saved.path.read_bytes() == b"log"
