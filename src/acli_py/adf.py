"""Convert between the Markdown people type and Jira's Atlassian Document Format (ADF).

Jira Cloud's v3 API takes rich text (descriptions, comments, worklog notes, multi-line custom
fields) as ADF JSON. `to_adf` accepts a small, predictable Markdown subset:

- paragraphs, with single newlines kept as line breaks
- `#` to `######` headings, `-`/`*`/`+` bullet lists, `1.` numbered lists (indent to nest)
- fenced code blocks with an optional language, `>` quotes, `---` rules
- inline `code`, **bold**, *italic* or _italic_, ~~strike~~, [links](https://…) and bare URLs

Text that already is an ADF document (JSON with `"type": "doc"`) passes through unchanged.
`to_text` goes the other way, producing Markdown suitable for the terminal.
"""

from __future__ import annotations

import json
import re
from typing import Any

Node = dict[str, Any]

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_FENCE = re.compile(r"^\s*```\s*([\w+-]*)\s*$")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_INLINE = re.compile(
    r"`(?P<code>[^`]+)`"
    r"|\*\*(?P<strong>.+?)\*\*"
    r"|~~(?P<strike>.+?)~~"
    r"|\[(?P<label>[^\]]+)\]\((?P<href>[^)\s]+)\)"
    r"|(?<![\w*])\*(?![\s*])(?P<em>.+?)(?<![\s*])\*(?![\w*])"
    r"|(?<![\w_])_(?![\s_])(?P<em2>.+?)(?<![\s_])_(?![\w_])"
    r"|(?P<url>https?://[^\s<>()\[\]]+[^\s<>()\[\].,;:!?'\"])"
)


def is_adf(value: Any) -> bool:
    """Return whether `value` is an ADF document."""
    return isinstance(value, dict) and value.get("type") == "doc"


def parse_adf(text: str) -> Node | None:
    """Return `text` parsed as an ADF document, or None when it is not one."""
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        data = json.loads(stripped)
    except ValueError:
        return None
    return data if is_adf(data) else None


# ── Markdown → ADF ───────────────────────────────────────────────────────────


def to_adf(text: str) -> Node:
    """Convert Markdown-ish text (or an ADF JSON string) to an ADF document."""
    if (doc := parse_adf(text)) is not None:
        return doc
    lines = text.replace("\r\n", "\n").replace("\t", "    ").split("\n")
    return {"type": "doc", "version": 1, "content": _blocks(lines)}


def _blocks(lines: list[str]) -> list[Node]:
    blocks: list[Node] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif fence := _FENCE.match(line):
            end = i + 1
            while end < len(lines) and not _FENCE.match(lines[end]):
                end += 1
            code = "\n".join(lines[i + 1 : end])
            node: Node = {"type": "codeBlock", "content": [{"type": "text", "text": code}]}
            if not code:
                del node["content"]
            if fence.group(1):
                node["attrs"] = {"language": fence.group(1)}
            blocks.append(node)
            i = end + 1
        elif heading := _HEADING.match(line):
            blocks.append(
                {
                    "type": "heading",
                    "attrs": {"level": len(heading.group(1))},
                    "content": inline(heading.group(2).strip()),
                }
            )
            i += 1
        elif _RULE.match(line):
            blocks.append({"type": "rule"})
            i += 1
        elif _QUOTE.match(line):
            quoted: list[str] = []
            while i < len(lines) and (m := _QUOTE.match(lines[i])):
                quoted.append(m.group(1))
                i += 1
            blocks.append({"type": "blockquote", "content": _blocks(quoted) or [_para("")]})
        elif _BULLET.match(line) or _ORDERED.match(line):
            node, i = _list(lines, i)
            blocks.append(node)
        else:
            para: list[str] = []
            while i < len(lines) and lines[i].strip() and not _starts_block(lines[i]):
                para.append(lines[i].strip())
                i += 1
            blocks.append(_para("\n".join(para)))
    return blocks


def _starts_block(line: str) -> bool:
    return any(p.match(line) for p in (_FENCE, _HEADING, _RULE, _QUOTE, _BULLET, _ORDERED))


def _item_match(line: str) -> tuple[int, bool, str] | None:
    """Return (indent, ordered, text) when `line` is a list item."""
    if m := _BULLET.match(line):
        return len(m.group(1)), False, m.group(2)
    if m := _ORDERED.match(line):
        return len(m.group(1)), True, m.group(3)
    return None


def _list(lines: list[str], i: int) -> tuple[Node, int]:
    first = _item_match(lines[i])
    assert first is not None
    indent, ordered, _ = first
    node: Node = {"type": "orderedList" if ordered else "bulletList", "content": []}
    if ordered and (m := _ORDERED.match(lines[i])) and m.group(2) != "1":
        node["attrs"] = {"order": int(m.group(2))}
    while i < len(lines):
        item = _item_match(lines[i])
        if item is None or item[0] < indent or (item[0] == indent and item[1] != ordered):
            break
        if item[0] > indent:  # a nested list under the previous item
            nested, i = _list(lines, i)
            node["content"][-1]["content"].append(nested)
            continue
        node["content"].append({"type": "listItem", "content": [_para(item[2])]})
        i += 1
        # Indented continuation lines belong to the item's paragraph.
        while (
            i < len(lines)
            and lines[i].strip()
            and _item_match(lines[i]) is None
            and len(lines[i]) - len(lines[i].lstrip()) > indent
        ):
            para = node["content"][-1]["content"][0]
            para["content"] = [
                *para.get("content", []),
                {"type": "hardBreak"},
                *inline(lines[i].strip()),
            ]
            i += 1
    return node, i


def _para(text: str) -> Node:
    content: list[Node] = []
    for n, line in enumerate(text.split("\n")):
        if n:
            content.append({"type": "hardBreak"})
        content.extend(inline(line))
    node: Node = {"type": "paragraph"}
    if content:
        node["content"] = content
    return node


def inline(text: str) -> list[Node]:
    """Convert one line of Markdown inline syntax to ADF text nodes."""
    nodes: list[Node] = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            nodes.append({"type": "text", "text": text[pos : m.start()]})
        kind = m.lastgroup
        if kind == "code":
            nodes.append(_text(m.group("code"), {"type": "code"}))
        elif kind == "strong":
            nodes.append(_text(m.group("strong"), {"type": "strong"}))
        elif kind == "strike":
            nodes.append(_text(m.group("strike"), {"type": "strike"}))
        elif kind == "href":
            link = {"type": "link", "attrs": {"href": m.group("href")}}
            nodes.append(_text(m.group("label"), link))
        elif kind in ("em", "em2"):
            nodes.append(_text(m.group(kind), {"type": "em"}))
        else:
            url = m.group("url")
            nodes.append(_text(url, {"type": "link", "attrs": {"href": url}}))
        pos = m.end()
    if pos < len(text):
        nodes.append({"type": "text", "text": text[pos:]})
    return nodes


def _text(text: str, mark: Node) -> Node:
    return {"type": "text", "text": text, "marks": [mark]}


# ── ADF → Markdown ───────────────────────────────────────────────────────────


def to_text(doc: Any) -> str:
    """Render an ADF document (or a plain string) as Markdown text."""
    if doc is None:
        return ""
    if isinstance(doc, str):
        return doc
    if not isinstance(doc, dict):
        return str(doc)
    return "\n\n".join(b for b in (_block(n, 0) for n in doc.get("content", [])) if b).strip()


def _block(node: Node, depth: int) -> str:
    kind = node.get("type")
    children = node.get("content", [])
    if kind == "paragraph":
        return _inline(children)
    if kind == "heading":
        return "#" * int(node.get("attrs", {}).get("level", 1)) + " " + _inline(children)
    if kind in ("bulletList", "orderedList"):
        start = int(node.get("attrs", {}).get("order", 1))
        items = []
        for n, item in enumerate(children):
            marker = f"{start + n}." if kind == "orderedList" else "-"
            items.append(_list_item(item, marker, depth))
        return "\n".join(items)
    if kind == "codeBlock":
        lang = node.get("attrs", {}).get("language") or ""
        return f"```{lang}\n{_inline(children)}\n```"
    if kind == "blockquote":
        inner = "\n\n".join(_block(c, depth) for c in children)
        return "\n".join(f"> {line}" if line else ">" for line in inner.split("\n"))
    if kind == "rule":
        return "---"
    if kind in ("panel", "expand", "nestedExpand", "layoutSection", "layoutColumn"):
        title = node.get("attrs", {}).get("title")
        inner = "\n\n".join(_block(c, depth) for c in children)
        return f"**{title}**\n\n{inner}" if title else inner
    if kind == "table":
        return _table(node)
    if kind in ("mediaSingle", "mediaGroup"):
        return "[attachment]"
    if kind in ("blockCard", "embedCard"):
        return str(node.get("attrs", {}).get("url", ""))
    return _inline(children) if children else ""


def _list_item(item: Node, marker: str, depth: int) -> str:
    pad = "  " * depth
    parts: list[str] = []
    for child in item.get("content", []):
        if child.get("type") in ("bulletList", "orderedList"):
            parts.append(_block(child, depth + 1))
        else:
            text = _block(child, depth).replace("\n", "\n" + pad + "  ")
            parts.append(f"{pad}{marker} {text}" if not parts else f"{pad}  {text}")
    return "\n".join(parts) or f"{pad}{marker}"


def _table(node: Node) -> str:
    rows = []
    for row in node.get("content", []):
        cells = [
            " ".join(_block(c, 0) for c in cell.get("content", [])).replace("\n", " ")
            for cell in row.get("content", [])
        ]
        rows.append("| " + " | ".join(cells) + " |")
    if rows:
        width = rows[0].count("|") - 1
        rows.insert(1, "|" + " --- |" * width)
    return "\n".join(rows)


def _inline(nodes: list[Node]) -> str:
    out: list[str] = []
    for node in nodes:
        kind = node.get("type")
        attrs = node.get("attrs", {})
        if kind == "text":
            out.append(_marked(node.get("text", ""), node.get("marks", [])))
        elif kind == "hardBreak":
            out.append("\n")
        elif kind == "mention":
            text = attrs.get("text") or attrs.get("id", "someone")
            out.append(text if text.startswith("@") else f"@{text}")
        elif kind == "emoji":
            out.append(attrs.get("text") or attrs.get("shortName", ""))
        elif kind == "inlineCard":
            out.append(attrs.get("url", ""))
        elif kind == "status":
            out.append(f"[{attrs.get('text', '')}]")
        elif kind == "date":
            out.append(str(attrs.get("timestamp", "")))
        elif "content" in node:
            out.append(_inline(node["content"]))
    return "".join(out)


def _marked(text: str, marks: list[Node]) -> str:
    for mark in marks:
        kind = mark.get("type")
        if kind == "code":
            text = f"`{text}`"
        elif kind == "strong":
            text = f"**{text}**"
        elif kind == "em":
            text = f"*{text}*"
        elif kind == "strike":
            text = f"~~{text}~~"
        elif kind == "link":
            href = mark.get("attrs", {}).get("href", "")
            text = text if text == href else f"[{text}]({href})"
    return text
