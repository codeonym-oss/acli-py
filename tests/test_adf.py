from __future__ import annotations

import json

from acli_py.adf import inline, parse_adf, to_adf, to_text


def test_plain_text_becomes_paragraphs_with_line_breaks():
    doc = to_adf("first line\nsecond line\n\nnew paragraph")
    assert [b["type"] for b in doc["content"]] == ["paragraph", "paragraph"]
    assert [n["type"] for n in doc["content"][0]["content"]] == ["text", "hardBreak", "text"]


def test_inline_marks():
    nodes = inline("a **b** *c* _d_ ~~e~~ `f` [g](https://h.io) https://x.io/y.")
    marks = {n["text"]: n["marks"][0]["type"] for n in nodes if "marks" in n}
    assert marks == {
        "b": "strong", "c": "em", "d": "em", "e": "strike", "f": "code", "g": "link",
        "https://x.io/y": "link",
    }  # fmt: skip
    assert nodes[-1]["text"] == "."


def test_snake_case_and_lone_stars_stay_text():
    assert inline("snake_case_name and 2 * 3 * 4") == [
        {"type": "text", "text": "snake_case_name and 2 * 3 * 4"}
    ]


def test_blocks_and_nested_lists():
    doc = to_adf("# Title\n- a\n  - b\n- c\n1. one\n2. two\n> quote\n---\n```py\nx = 1\n```")
    kinds = [b["type"] for b in doc["content"]]
    assert kinds == ["heading", "bulletList", "orderedList", "blockquote", "rule", "codeBlock"]
    bullets = doc["content"][1]["content"]
    assert len(bullets) == 2
    assert bullets[0]["content"][1]["type"] == "bulletList"
    assert doc["content"][-1]["attrs"] == {"language": "py"}


def test_ordered_list_keeps_its_start():
    doc = to_adf("3. three\n4. four")
    assert doc["content"][0]["attrs"] == {"order": 3}
    assert to_text(doc) == "3. three\n4. four"


def test_adf_json_passes_through():
    doc = {"type": "doc", "version": 1, "content": []}
    assert to_adf(json.dumps(doc)) == doc
    assert parse_adf('{"not": "adf"}') is None
    assert parse_adf("{broken") is None


def test_markdown_round_trips():
    text = "## Plan\n\nDo **this** then `that`.\n\n- one\n- two\n  - deeper\n\n```\ncode\n```"
    assert to_text(to_adf(text)) == text


def test_to_text_renders_nodes_jira_produces():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "mention", "attrs": {"id": "1", "text": "@Alice"}},
                    {"type": "text", "text": " see "},
                    {"type": "inlineCard", "attrs": {"url": "https://x.io"}},
                    {"type": "emoji", "attrs": {"shortName": ":ok:", "text": "👍"}},
                    {"type": "status", "attrs": {"text": "DONE"}},
                ],
            },
            {"type": "panel", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "note"}]}]},
            {
                "type": "table",
                "content": [
                    {"type": "tableRow", "content": [
                        {"type": "tableHeader", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "h"}]}]},
                    ]},
                    {"type": "tableRow", "content": [
                        {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "v"}]}]},
                    ]},
                ],
            },
            {"type": "mediaSingle", "content": []},
        ],
    }  # fmt: skip
    assert (
        to_text(doc)
        == "@Alice see https://x.io👍[DONE]\n\nnote\n\n| h |\n| --- |\n| v |\n\n[attachment]"
    )
    assert to_text(None) == ""
    assert to_text("plain") == "plain"
