"""The resolvers and field builders, against a stub client (no HTTP)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from acli_py.infrastructure.jira import fields, resolve
from acli_py.infrastructure.jira.fields import IssueInput, text, when
from acli_py.infrastructure.jira.resolve import FieldCatalog, ResolveError
from tests import fake_jira

if TYPE_CHECKING:
    from pathlib import Path


class StubClient:
    """Answers the few reads the resolvers make, from the fake site's data."""

    def get(self, path, **params):
        assert path.endswith("/user/search")
        q = params["query"].lower()
        return [
            u for u in fake_jira.USERS if q in u["displayName"].lower() or q in u["emailAddress"]
        ]

    def myself(self):
        return fake_jira.ALICE

    def fields(self):
        return fake_jira.FIELDS

    def link_types(self):
        return fake_jira.LINK_TYPES


client: resolve.JiraClient = StubClient()  # type: ignore[assignment]


def field(schema: dict, name: str = "F") -> dict:
    return {"id": "customfield_1", "name": name, "schema": schema}


def test_split_and_read_keys(tmp_path):
    assert resolve.split_keys(["demo-1, DEMO-2", "demo-1 ops-3"]) == ["DEMO-1", "DEMO-2", "OPS-3"]
    keys = tmp_path / "k.txt"
    keys.write_text("DEMO-1\n\nDEMO-2;DEMO-3 # trailing note\n")
    assert resolve.read_keys_file(keys) == ["DEMO-1", "DEMO-2", "DEMO-3"]


def test_parse_assignment():
    assert resolve.parse_assignment("Story Points=5") == ("Story Points", "5", False)
    assert resolve.parse_assignment('Team:={"id": 1}') == ("Team", '{"id": 1}', True)
    assert resolve.parse_assignment("Note=a=b") == ("Note", "a=b", False)
    with pytest.raises(ResolveError):
        resolve.parse_assignment("no equals")
    with pytest.raises(ResolveError):
        resolve.parse_assignment("=value")


def test_users():
    assert resolve.account_id(client, "@me") == fake_jira.ALICE["accountId"]
    assert resolve.account_id(client, "me", "cached") == "cached"
    assert resolve.account_id(client, "default") == "-1"
    assert resolve.account_id(client, "none") is None
    assert resolve.account_id(client, "BOB@example.com") == fake_jira.BOB["accountId"]
    assert resolve.account_id(client, "carol") == fake_jira.CAROL["accountId"]
    assert resolve.account_id(client, "5b10ac8d82e05b22cc7d4ef5") == "5b10ac8d82e05b22cc7d4ef5"
    with pytest.raises(ResolveError, match="several people"):
        resolve.user(client, "jensen")


def test_field_catalog():
    catalog = FieldCatalog(fake_jira.FIELDS)
    assert catalog.find("story POINT estimate")["id"] == "customfield_10016"
    assert catalog.find("cf[10016]")["id"] == "customfield_10016"
    assert catalog.find("labels")["id"] == "labels"
    twins = FieldCatalog([{"id": "a", "name": "Same"}, {"id": "b", "name": "same"}])
    with pytest.raises(ResolveError, match="several fields"):
        twins.find("same")
    with pytest.raises(ResolveError, match="acli-py field list"):
        catalog.find("zzz")


@pytest.mark.parametrize(
    ("schema", "value", "expected"),
    [
        ({"type": "number"}, "2.5", 2.5),
        ({"type": "number"}, "3", 3),
        ({"type": "string"}, "plain", "plain"),
        ({"type": "option"}, "Blue", {"value": "Blue"}),
        (
            {"type": "option-with-child"},
            "Europe > Paris",
            {"value": "Europe", "child": {"value": "Paris"}},
        ),
        ({"type": "priority"}, "High", {"name": "High"}),
        ({"type": "priority"}, "2", {"id": "2"}),
        ({"type": "version"}, "2.4", {"name": "2.4"}),
        ({"type": "project"}, "demo", {"key": "DEMO"}),
        ({"type": "array", "items": "option"}, "a, b", [{"value": "a"}, {"value": "b"}]),
        ({"type": "array", "items": "version"}, "1,2", [{"name": "1"}, {"name": "2"}]),
        ({"type": "array", "items": "string"}, "x,y", ["x", "y"]),
        ({"type": "array", "items": "json", "custom": "x:gh-sprint"}, "7", 7),
        ({"type": "date"}, "2026-01-02", "2026-01-02"),
        ({}, '{"raw": true}', {"raw": True}),
        ({}, "not json", "not json"),
        ({"type": "user"}, "bob@example.com", {"accountId": fake_jira.BOB["accountId"]}),
    ],
)
def test_field_value_coercion(schema, value, expected):
    assert resolve.field_value(client, field(schema), value) == expected


def test_textarea_becomes_adf_and_bad_json_is_explained():
    doc = resolve.field_value(client, field({"type": "string", "custom": "x:textarea"}), "**hi**")
    assert doc["type"] == "doc"
    with pytest.raises(ResolveError, match="valid JSON"):
        resolve.field_values(client, ["Team:={nope"])


def test_read_text_arg(tmp_path, monkeypatch):
    import io

    note = tmp_path / "n.md"
    note.write_text("from file")
    assert resolve.read_text_arg(None, note) == "from file"
    assert resolve.read_text_arg("inline", None) == "inline"
    monkeypatch.setattr("sys.stdin", io.StringIO("piped"))
    assert resolve.read_text_arg("-", None) == "piped"
    assert resolve.read_text_arg(None, None) is None


def test_build_issue_fields():
    wanted = IssueInput(
        project="demo", type="10002", summary=" Title ", description="", assignee="default",
        reporter="@me", labels=["a"], components=["API"], fix_versions=["2.4"], priority="1",
        parent="demo-3", due="",
    )  # fmt: skip
    built = fields.build(client, wanted, creating=True)
    assert built == {
        "project": {"key": "DEMO"},
        "issuetype": {"id": "10002"},
        "summary": "Title",
        "description": None,
        "reporter": {"accountId": fake_jira.ALICE["accountId"]},
        "labels": ["a"],
        "components": [{"name": "API"}],
        "fixVersions": [{"name": "2.4"}],
        "priority": {"id": "1"},
        "parent": {"key": "DEMO-3"},
        "duedate": None,
    }
    assert fields.build(client, IssueInput(assignee="none"))["assignee"] is None
    assert fields.build(client, IssueInput(raw={"fields": {"x": 1}})) == {"x": 1}


def test_issue_input_from_mapping():
    item = IssueInput.from_mapping(
        {
            "Project-Key": "OPS",
            "components": "API; Web",
            "Team": "Red",
            "fields": {"Reviewers": ["a"]},
            "empty": "",
        }
    )
    assert item.project == "OPS"
    assert item.components == ["API", "Web"]
    assert item.extra == ["Team=Red", 'Reviewers:=["a"]']


def test_read_rows(tmp_path: Path):
    one = tmp_path / "one.json"
    one.write_text('{"summary": "x"}')
    assert fields.read_rows(one) == [{"summary": "x"}]
    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text('{"issueUpdates": [{"fields": {}}]}')
    assert fields.read_rows(wrapped) == [{"fields": {}}]


def test_display_helpers():
    assert when("2026-09-22T10:00:00.000+0200") == "2026-09-22 10:00"
    assert when("2026-09-22T10:00:00.000+0200", with_time=False) == "2026-09-22"
    assert when("garbage") == "garbage"
    assert when(None) == ""
    assert text(True) == "yes"
    assert text(2.50) == "2.5"
    assert text([{"name": "a"}, {"value": "b"}, None]) == "a, b"
    assert text({"value": "EU", "child": {"value": "Paris"}}) == "EU > Paris"
    assert text({"odd": 1}) == '{"odd": 1}'
    assert (
        text(
            {
                "type": "doc",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": "hi"}]}],
            }
        )
        == "hi"
    )
