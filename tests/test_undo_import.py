"""`acli-py log`, `undo` and `issue import`: the audit log read back, and rows into issues."""

from __future__ import annotations

import json

import pytest

from acli_py.domain import adf, edits
from acli_py.presentation import terminal
from acli_py.presentation.cli import common
from tests import fake_jira
from tests.conftest import run_cli


def ok(*args: str, input: str | None = None) -> str:
    result, out = run_cli(*args, input=input)
    assert result.exit_code == 0, out
    return out


def log() -> list[dict]:
    return json.loads(ok("log", "--json"))


# ── values ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ({"id": "3", "name": "Medium"}, {"name": "Medium"}, True),
        ({"id": "3", "name": "Medium"}, "Medium", True),
        ({"accountId": "x"}, "x", True),
        (["web", "docs"], ["docs", "web"], True),
        (["web"], ["web", "docs"], False),
        (None, [], True),
        ("", "x", False),
        (adf.to_adf("Hello  **you**"), adf.to_adf("Hello **you**"), True),
    ],
)
def test_values_are_equal_however_jira_spells_them(a, b, expected):
    assert edits.equal(a, b) is expected


def test_values_go_back_by_what_names_them():
    medium = {"self": "http://x", "id": "3", "name": "Medium", "iconUrl": "http://y"}
    assert edits.as_input(medium) == {"id": "3"}
    assert edits.as_input([{"name": "API"}, "web"]) == [{"name": "API"}, "web"]
    doc = adf.to_adf("text")
    assert edits.as_input(doc) == doc


# ── log and undo ─────────────────────────────────────────────────────────────


def test_undo_puts_an_edit_back_and_says_so_in_the_log(site):
    ok("issue", "edit", "DEMO-1", "DEMO-2", "-P", "Low", "--add-label", "q4", "-y")
    assert site.issues["DEMO-1"]["fields"]["priority"]["name"] == "Low"
    out = ok("undo", "-y")
    assert "2 of 2 put back." in out
    for key, labels in (("DEMO-1", ["web"]), ("DEMO-2", ["docs"])):
        assert site.issues[key]["fields"]["priority"]["name"] == "Medium"
        assert site.issues[key]["fields"]["labels"] == labels
    edit, undo = reversed(log())
    assert (edit["id"], edit["undoneBy"]) == ("1", "2")
    assert (undo["command"], undo["undoes"]) == ("EditIssue", "1")
    assert "undone by 2" in ok("log")


def test_undo_moves_back_and_reassigns(site):
    ok("issue", "transition", "DEMO-1", "--to", "Done", "-y")
    ok("issue", "assign", "DEMO-1", "--to", "bob@example.com", "-y")
    ok("undo", "-y")  # the assignment, the last change
    assert site.issues["DEMO-1"]["fields"]["assignee"] == fake_jira.ALICE
    ok("undo", "-y")  # then the transition: an undo is never undone by `undo` alone
    assert site.issues["DEMO-1"]["fields"]["status"]["name"] == "To Do"
    result, out = run_cli("undo")
    assert result.exit_code == 1
    assert "Nothing to undo" in out


def test_undo_flags_issues_changed_since_and_asks_once(site, monkeypatch):
    ok("issue", "edit", "DEMO-1", "DEMO-2", "-P", "Low", "-y")
    ok("issue", "edit", "DEMO-2", "-P", "High", "-y")
    monkeypatch.setattr(common, "interactive", lambda: True)
    asked: list[str] = []
    monkeypatch.setattr(terminal, "ask", lambda q: asked.append(q) or False)
    result, out = run_cli("undo", "1")
    assert result.exit_code == 2
    assert "DEMO-2 changed again since change 1; undoing sets it back anyway." in out
    assert asked == ["Undo 2 issues (DEMO-1, DEMO-2) (change 1, EditIssue)?"]
    assert "High (changed since)" in out
    assert site.issues["DEMO-1"]["fields"]["priority"]["name"] == "Low"


def test_undo_reports_what_it_cannot_put_back(site):
    ok("issue", "comment", "add", "DEMO-1", "-b", "hi")
    result, out = run_cli("undo")
    assert result.exit_code == 1
    assert "(CommentOnIssue) can't be undone" in out
    ok("issue", "edit", "DEMO-1", "-P", "Low", "-y")
    ok("issue", "edit", "DEMO-1", "-P", "Medium", "-y")
    result, out = run_cli("undo", "2", "-y")
    assert result.exit_code == 1
    assert "DEMO-1: not undone, it is as it was already." in out
    result, out = run_cli("undo", "9")
    assert "No change 9 in the log" in out
    ok("undo", "3", "-y")
    result, out = run_cli("undo", "3")
    assert "Change 3 was undone already, by change 4." in out


def test_undo_in_a_dry_run_changes_nothing(site):
    ok("issue", "edit", "DEMO-1", "-P", "Low", "-y")
    site.log.clear()
    out = ok("undo", "--dry-run")
    assert "would be put back" in out
    assert site.writes() == []
    assert log()[0]["undoneBy"] is None


# ── import ───────────────────────────────────────────────────────────────────


def test_import_updates_by_key_creates_the_rest_and_undo_puts_edits_back(site, tmp_path):
    rows = tmp_path / "rows.csv"
    rows.write_text(
        "key,summary,priority,labels,status\n"
        "DEMO-1,Login fails on Safari,High,web,Done\n"  # priority changes; status is skipped
        "DEMO-2,Write release notes,Medium,docs,To Do\n"  # as it is already
        ",Plan the offsite,Low,,\n"  # new, in --project
    )
    out = ok("issue", "import", str(rows), "-p", "OPS", "-y")
    assert "(matches issues by key)" in out
    assert "(skipped: read-only)" in out
    assert "1 row match their issue already." in out
    assert "2 of 2 imported." in out
    assert site.issues["DEMO-1"]["fields"]["priority"]["name"] == "High"
    assert site.issues["DEMO-1"]["fields"]["status"]["name"] == "To Do"
    new = site.issues["OPS-2"]["fields"]
    assert (new["summary"], new["priority"]["name"]) == ("Plan the offsite", "Low")
    (record,) = log()
    assert record["command"] == "ImportIssues"
    result, out = run_cli("undo", "-y")
    assert result.exit_code == 1  # the new issue stays: undo doesn't delete
    assert "OPS-2: not undone, it was created; delete it to undo that." in out
    assert site.issues["DEMO-1"]["fields"]["priority"]["name"] == "Medium"


def test_import_round_trips_an_export(site, tmp_path):
    exported = ok("issue", "search", "project = DEMO", "--fields", "key,summary,priority,labels",
                  "--output", "jsonl")  # fmt: skip
    rows = [json.loads(line) for line in exported.splitlines()]
    rows[0]["labels"] = ["web", "safari"]
    edited = tmp_path / "edited.jsonl"
    edited.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    out = ok("issue", "import", str(edited), "-y")
    assert "DEMO-1 imported" in out
    assert "2 rows match their issue already." in out
    assert site.issues["DEMO-1"]["fields"]["labels"] == ["web", "safari"]
    edits_sent = [p for m, p, _ in site.writes() if m == "PUT"]
    assert edits_sent == ["/rest/api/3/issue/DEMO-1"]


def test_import_refuses_unknown_columns_and_reports_bad_rows(site, tmp_path):
    rows = tmp_path / "rows.csv"
    rows.write_text("key,summary,Mood\nDEMO-1,x,happy\n")
    result, out = run_cli("issue", "import", str(rows))
    assert result.exit_code == 1
    assert "No field is called 'Mood'" in out
    rows.write_text("key,summary\nDEMO-99,x\n,no project\n")
    result, out = run_cli("issue", "import", str(rows))
    assert result.exit_code == 1
    assert "DEMO-99: not found" in out
    assert "#2: no project" in out
    assert site.writes() == []


def test_import_reads_the_csv_a_search_prints(site, tmp_path):
    exported = ok("issue", "search", "project = DEMO", "--fields",
                  "key,summary,status,priority,labels,fixVersions,due", "--csv")  # fmt: skip
    edited = tmp_path / "open.csv"
    edited.write_text(exported.replace("Write release notes", "Write the release notes"))
    out = ok("issue", "import", str(edited), "-y")
    assert "✔ DEMO-2 imported\n" in out
    assert site.issues["DEMO-2"]["fields"]["summary"] == "Write the release notes"


# ── export ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["--as", "csv"], "key,summary,priority\nDEMO-1,Login fails on Safari,Medium\n"),
        (
            ["--as", "jsonl"],
            '{"key": "DEMO-1", "summary": "Login fails on Safari", "priority": "Medium"}\n',
        ),
        (
            ["--as", "markdown"],
            "| key | summary | priority |\n|---|---|---|\n| DEMO-1 | Login fails on Safari | Medium |\n",
        ),
    ],
    ids=["csv", "jsonl", "markdown"],
)
def test_export_writes_each_format(site, args, expected):
    out = ok("issue", "export", "key in (DEMO-1)", "--fields", "summary,priority", *args)
    assert out == expected


def test_export_streams_every_page_to_a_file_and_json_stays_valid(site, tmp_path, monkeypatch):
    from acli_py.application.queries.export_issues import handler

    monkeypatch.setattr(handler, "PAGE", 2)  # three issues: two pages
    target = tmp_path / "demo.json"
    out = ok("issue", "export", "project = DEMO", "-o", str(target))
    assert "Wrote 3 issues to" in out
    assert [r["key"] for r in json.loads(target.read_text())] == ["DEMO-1", "DEMO-2", "DEMO-3"]
    searches = [b for m, p, b in site.log if p == "/rest/api/3/search/jql"]
    assert [b["maxResults"] for b in searches] == [2, 2]
    assert json.loads(ok("issue", "export", "key in (NOPE-1)", "--as", "json")) == []
    assert (
        len(ok("issue", "export", "project = DEMO", "--limit", "2", "--as", "jsonl").splitlines())
        == 2
    )


def test_export_then_import_round_trips_through_csv(site, tmp_path):
    target = tmp_path / "demo.csv"
    ok(
        "issue",
        "export",
        "project = DEMO",
        "--fields",
        "summary,priority,labels,due",
        "-o",
        str(target),
    )
    target.write_text(
        target.read_text().replace("DEMO-3,Speed up search,Medium", "DEMO-3,Speed up search,High")
    )
    out = ok("issue", "import", str(target), "-y")
    assert "2 rows match their issue already." in out
    assert site.issues["DEMO-3"]["fields"]["priority"]["name"] == "High"


# ── review fixes ─────────────────────────────────────────────────────────────


def test_an_undo_that_failed_somewhere_can_be_finished(site):
    from datetime import UTC, datetime

    from acli_py.application.changes import AuditRecord
    from acli_py.infrastructure.audit import AuditFile

    ok("issue", "edit", "DEMO-1", "DEMO-2", "-P", "Low", "-y")
    site.issues["DEMO-1"]["fields"]["priority"] = next(
        p for p in fake_jira.PRIORITIES if p["name"] == "Medium"
    )
    # An undo that put DEMO-1 back but failed on DEMO-2 leaves change 1 open.
    AuditFile().record(
        AuditRecord("EditIssue", (), datetime.now(UTC), {"DEMO-2": "try again"}, undoes="1")
    )
    assert log()[-1]["undoneBy"] is None
    result, out = run_cli("undo", "-y")
    assert result.exit_code == 1  # DEMO-1 is skipped: it is back already
    assert "DEMO-1: not undone, it is as it was already." in out
    assert site.issues["DEMO-2"]["fields"]["priority"]["name"] == "Medium"
    assert log()[-1]["undoneBy"] == "3"


def test_undo_skips_issues_deleted_since(site):
    ok("issue", "edit", "DEMO-1", "DEMO-2", "-P", "Low", "-y")
    del site.issues["DEMO-2"]
    result, out = run_cli("undo", "-y")
    assert result.exit_code == 1
    assert "DEMO-2: not undone" in out
    assert site.issues["DEMO-1"]["fields"]["priority"]["name"] == "Medium"


def test_undo_of_an_assignment_to_the_default_is_not_flagged_as_changed_since(site):
    ok("issue", "assign", "DEMO-1", "--to", "default", "-y")
    out = ok("undo", "-y")
    assert "changed again" not in out
    assert site.issues["DEMO-1"]["fields"]["assignee"] == fake_jira.ALICE


def test_import_refuses_a_key_twice(site, tmp_path):
    rows = tmp_path / "rows.csv"
    rows.write_text("key,priority\nDEMO-1,High\ndemo-1,Low\n")
    result, out = run_cli("issue", "import", str(rows), "-y")
    assert result.exit_code == 1
    assert "row 2 repeats the key" in out
    assert site.issues["DEMO-1"]["fields"]["priority"]["name"] == "High"


def test_a_failed_export_leaves_the_file_as_it_was(site, tmp_path):
    target = tmp_path / "keep.csv"
    target.write_text("precious\n")
    site.fail_next[:] = [400]
    result, _ = run_cli("issue", "export", "project = DEMO", "-o", str(target))
    assert result.exit_code == 1
    assert target.read_text() == "precious\n"
    assert not list(tmp_path.glob(".*.part"))
