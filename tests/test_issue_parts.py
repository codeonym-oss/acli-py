from __future__ import annotations

import json

from acli_py.adf import to_text
from tests import fake_jira
from tests.conftest import run_cli


def ok(*args: str, input: str | None = None) -> str:
    result, out = run_cli(*args, input=input)
    assert result.exit_code == 0, out
    return out


# ── comments ─────────────────────────────────────────────────────────────────


def test_comment_add_list_edit_delete(site):
    out = ok("issue", "comment", "add", "DEMO-2", "-b", "Looks **good**", "--role", "Developers")
    assert "DEMO-2 commented" in out
    comment = site.issues["DEMO-2"]["comments"][-1]
    assert comment["visibility"] == {"type": "role", "value": "Developers"}
    assert to_text(comment["body"]) == "Looks **good**"

    out = ok("issue", "comment", "list", "DEMO-2")
    assert "Looks good" in out  # rendered as Markdown
    assert "visible to Developers" in out
    data = json.loads(ok("issue", "comment", "list", "DEMO-2", "--json", "--newest-first"))
    assert data[0]["id"] == comment["id"]

    ok("issue", "comment", "edit", "DEMO-2", comment["id"], "-b", "Changed")
    assert to_text(comment["body"]) == "Changed"
    ok("issue", "comment", "delete", "DEMO-2", comment["id"], "-y")
    assert site.issues["DEMO-2"]["comments"] == []
    assert "has no comments" in ok("issue", "comment", "list", "DEMO-2")


def test_comment_from_stdin_on_many_issues(site):
    out = ok(
        "issue", "comment", "add", "--jql", "project = DEMO", "-b", "-", "-y", input="Deployed\n"
    )
    assert "3 of 3 commented" in out
    assert to_text(site.issues["DEMO-3"]["comments"][-1]["body"]) == "Deployed"


def test_comment_edit_last_replaces_my_latest(site):
    ok("issue", "comment", "add", "DEMO-2", "-b", "first")
    ok("issue", "comment", "add", "DEMO-2", "-b", "second", "--edit-last")
    comments = site.issues["DEMO-2"]["comments"]
    assert [to_text(c["body"]) for c in comments] == ["second"]


def test_comment_needs_a_body_and_one_visibility(site, tmp_path):
    result, out = run_cli("issue", "comment", "add", "DEMO-2")
    assert result.exit_code == 1
    assert "comment is empty" in out
    result, out = run_cli(
        "issue", "comment", "add", "DEMO-2", "-b", "x", "--role", "a", "--group", "b"
    )
    assert "not both" in out
    body = tmp_path / "c.md"
    body.write_text("from a file")
    result, out = run_cli("issue", "comment", "add", "DEMO-2", "-b", "x", "-B", str(body))
    assert "not both" in out
    ok("issue", "comment", "add", "DEMO-2", "-B", str(body))


def test_comment_visibility_options(site):
    assert "Developers" in ok("issue", "comment", "visibility", "-p", "DEMO")
    assert "jira-users" in ok("issue", "comment", "visibility")


# ── links ────────────────────────────────────────────────────────────────────


def test_link_add_reads_as_a_sentence(site):
    ok("issue", "link", "add", "DEMO-2", "blocks", "DEMO-3")
    ok("issue", "link", "add", "DEMO-2", "is duplicated by", "OPS-1", "-m", "Same thing")
    links = list(site.links.values())
    assert {"type": "Blocks", "outward": "DEMO-2", "inward": "DEMO-3"} in links
    # "DEMO-2 is duplicated by OPS-1" is "OPS-1 duplicates DEMO-2".
    assert {"type": "Duplicate", "outward": "OPS-1", "inward": "DEMO-2"} in links
    assert to_text(site.issues["OPS-1"]["comments"][-1]["body"]) == "Same thing"
    out = ok("issue", "link", "list", "DEMO-2")
    assert "blocks" in out
    assert "is duplicated by" in out


def test_link_errors(site):
    result, out = run_cli("issue", "link", "add", "DEMO-1", "fixes", "DEMO-2")
    assert result.exit_code == 1
    assert "no link type 'fixes'" in out
    assert "Blocks (blocks / is blocked by)" in out
    result, out = run_cli("issue", "link", "add", "DEMO-1", "blocks")
    assert "Give three words" in out


def test_links_from_files_and_delete(site, tmp_path):
    spec = tmp_path / "links.json"
    spec.write_text(json.dumps([{"from": "DEMO-2", "type": "relates to", "to": "DEMO-3"}]))
    sheet = tmp_path / "links.csv"
    sheet.write_text("from,type,to\nOPS-1,blocks,DEMO-2\n")
    out = ok("issue", "link", "add", "--from-json", str(spec), "--from-csv", str(sheet), "-y")
    assert "2 of 2 linked" in out
    ids = json.loads(ok("issue", "link", "list", "DEMO-2", "--json"))
    link_ids = [link["id"] for link in ids]
    assert len(link_ids) == 2
    ok("issue", "link", "delete", ",".join(link_ids), "-y")
    assert "has no links" in ok("issue", "link", "list", "DEMO-2")
    _, out = run_cli("issue", "link", "delete")
    assert "Which links" in out


def test_link_types(site):
    out = ok("issue", "link", "types")
    assert "is cloned by" in out


# ── attachments ──────────────────────────────────────────────────────────────


def test_attachment_upload_list_download_delete(site, tmp_path):
    report = tmp_path / "report.txt"
    report.write_text("crash log\n")
    assert "Attached report.txt" in ok("issue", "attachment", "upload", "DEMO-1", str(report))
    files = json.loads(ok("issue", "attachment", "list", "DEMO-1", "--json"))
    assert [f["filename"] for f in files] == ["report.txt"]
    out_dir = tmp_path / "downloads"
    ok("issue", "attachment", "download", files[0]["id"], "-o", str(out_dir))
    assert (out_dir / "report.txt").read_text() == "crash log\n"
    ok("issue", "attachment", "delete", files[0]["id"], "-y")
    assert "has no attachments" in ok("issue", "attachment", "list", "DEMO-1")


def test_attachment_upload_dry_run_names_the_file(site, tmp_path):
    report = tmp_path / "report.txt"
    report.write_text("x")
    out = ok("issue", "attachment", "upload", "DEMO-1", str(report), "--dry-run")
    assert "upload: report.txt" in out
    assert site.writes() == []


# ── watchers and worklogs ────────────────────────────────────────────────────


def test_watchers(site):
    ok("issue", "watcher", "add", "DEMO-1", "bob@example.com")
    assert fake_jira.BOB in site.issues["DEMO-1"]["watchers"]
    assert "Bob Jensen" in ok("issue", "watcher", "list", "DEMO-1")
    ok("issue", "watcher", "remove", "DEMO-1")
    assert site.issues["DEMO-1"]["watchers"] == [fake_jira.BOB]


def test_worklogs(site):
    ok("issue", "worklog", "add", "DEMO-1", "1h 30m", "-m", "Pairing", "--started", "2026-09-24")
    log = site.issues["DEMO-1"]["worklogs"][0]
    assert log["timeSpent"] == "1h 30m"
    assert log["started"].startswith("2026-09-24T09:00:00.000")
    out = ok("issue", "worklog", "list", "DEMO-1")
    assert "1h 30m" in out
    assert "Pairing" in out
    ok("issue", "worklog", "delete", "DEMO-1", log["id"], "-y")
    assert site.issues["DEMO-1"]["worklogs"] == []
    result, out = run_cli("issue", "worklog", "add", "DEMO-1", "a while")
    assert result.exit_code == 1
    assert "not a duration" in out
