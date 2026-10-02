"""What the user typed or piped in: issue keys, text, and rows of issues (CSV, JSON).

Commands that act on issues take keys on the command line, '-' for stdin, or a file; these
read them. Searching (--jql, --filter) goes through the bus, in `cli.common.pick_issues`.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*-\d+$")
TARGET_SPLIT = re.compile(r"[\s,;]+")
STDIN = "-"  # in place of keys or a file: read them from standard input


class InputError(ValueError):
    """What was typed or piped in can't be read."""


def split_keys(values: list[str] | None) -> list[str]:
    """Split comma/space separated keys, upper-cased, de-duplicated in order."""
    keys: list[str] = []
    for value in values or []:
        for part in TARGET_SPLIT.split(value.strip()):
            if part and part.upper() not in keys:
                keys.append(part.upper())
    return keys


def keys_in(text: str) -> list[str]:
    """Return the issue keys or ids in `text`, whichever way it lists them.

    Plain keys separated by commas, spaces or new lines ('#' starts a comment), JSON lines
    (`--output jsonl`), or a JSON array (`--json`); a JSON item gives its `key`, else its `id`.
    """
    if text.lstrip().startswith("["):
        try:
            items = json.loads(text)
        except ValueError:
            raise InputError("the input starts like a JSON array but isn't valid JSON") from None
        return split_keys([_key_of(item) for item in items])
    found: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if line.startswith("{"):
            try:
                item = json.loads(line)
            except ValueError:
                raise InputError(f"line {number} starts like JSON but isn't valid JSON") from None
            found.append(_key_of(item))
        else:
            found.append(line.split("#", 1)[0])
    return split_keys(found)


def _key_of(item: Any) -> str:
    """Return the key a JSON item names: its `key`, else its `id`, or the item itself."""
    if not isinstance(item, dict):
        return str(item)
    value = item.get("key") or item.get("id")
    if value is None:
        raise InputError(f"a JSON item has no key or id: {json.dumps(item)[:60]}")
    return str(value)


def read_keys_file(path: Path) -> list[str]:
    """Read issue keys or ids from a file, or from stdin when it is '-' (see `keys_in`)."""
    text = sys.stdin.read() if str(path) == STDIN else path.read_text(encoding="utf-8")
    return keys_in(text)


def given(values: list[str] | None) -> list[str]:
    """Return the keys typed on the command line; a lone '-' reads more from stdin."""
    typed = [v for v in values or [] if v.strip() != STDIN]
    found = split_keys(typed)
    if len(typed) != len(values or []):
        found += [k for k in keys_in(sys.stdin.read()) if k not in found]
    return found


def check_keys(keys: list[str]) -> list[str]:
    """Return the keys, refusing any that is neither an issue key (DEMO-12) nor an id."""
    for key in keys:
        if not KEY_RE.match(key) and not key.isdigit():
            raise InputError(f"{key!r} is not an issue key (like DEMO-12) or id")
    return keys


def read_text_arg(text: str | None, file: Path | None) -> str | None:
    """Return text from an option, a file, or stdin when either is '-'."""
    if text is not None and file is not None:
        raise InputError("give the text inline or as a file, not both")
    if text == STDIN or (file is not None and str(file) == STDIN):
        return sys.stdin.read()
    if file is not None:
        return file.read_text(encoding="utf-8")
    return text


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Read issues from a JSON file (an object, a list or JSON lines) or a CSV file with a header.

    '-' reads JSON or JSON lines from stdin (`issue search --output jsonl | issue create …`).
    """
    if str(path) == "-":
        return parse_rows(sys.stdin.read())
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".csv":
        return [dict(row) for row in csv.DictReader(text.splitlines())]
    return parse_rows(text)


def parse_rows(text: str) -> list[dict[str, Any]]:
    """Return the issues in JSON text: one object, a list (or `{"issues": […]}`), or JSON lines."""
    text = text.lstrip("\ufeff")
    if not text.strip():
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) < 2:
            raise InputError(f"not JSON or JSON lines: {error}") from error
        data = []
        for number, line in enumerate(lines, 1):
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError as bad:
                raise InputError(f"line {number} is not JSON: {bad}") from bad
    if isinstance(data, dict) and isinstance(data.get("issues"), list):
        data = data["issues"]
    if isinstance(data, dict) and isinstance(data.get("issueUpdates"), list):
        data = data["issueUpdates"]
    rows = data if isinstance(data, list) else [data]
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise InputError(f"issue {number} is not a JSON object")
    return rows
