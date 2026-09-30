"""Turn what people type into what Jira's API wants.

People type `@me`, an email, part of a name, "Story Points=5", "In Progress" or "blocks";
Jira wants account ids, `customfield_10016: 5.0` and a link type with a
direction. Everything here raises `ResolveError` with a message that says what would work.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from acli_py.domain import adf
from acli_py.infrastructure.jira.client import API

if TYPE_CHECKING:
    from pathlib import Path

    from acli_py.infrastructure.jira.client import JiraClient

KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*-\d+$")
ACCOUNT_ID_RE = re.compile(r"^(?:\d+:[0-9a-f-]{36}|[0-9a-f]{24}|qm:[\w:-]+)$", re.IGNORECASE)
TARGET_SPLIT = re.compile(r"[\s,;]+")
STDIN = "-"  # in place of keys or a file: read them from standard input
CUSTOM = "com.atlassian.jira.plugin.system.customfieldtypes:"

# Sentinels for assignee-like options.
ME = ("@me", "me")
DEFAULT = "default"
NOBODY = ("none", "unassigned", "nobody", "-")


class ResolveError(ValueError):
    """What the user typed could not be matched to one thing in Jira."""


# ── issues to act on ─────────────────────────────────────────────────────────


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
            raise ResolveError("the input starts like a JSON array but isn't valid JSON") from None
        return split_keys([_key_of(item) for item in items])
    found: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if line.startswith("{"):
            try:
                item = json.loads(line)
            except ValueError:
                raise ResolveError(f"line {number} starts like JSON but isn't valid JSON") from None
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
        raise ResolveError(f"a JSON item has no key or id: {json.dumps(item)[:60]}")
    return str(value)


def read_keys_file(path: Path) -> list[str]:
    """Read issue keys or ids from a file, or from stdin when it is '-' (see `keys_in`)."""
    import sys

    text = sys.stdin.read() if str(path) == STDIN else path.read_text(encoding="utf-8")
    return keys_in(text)


def given(values: list[str] | None) -> list[str]:
    """Return the keys typed on the command line; a lone '-' reads more from stdin."""
    import sys

    typed = [v for v in values or [] if v.strip() != STDIN]
    found = split_keys(typed)
    if len(typed) != len(values or []):
        found += [k for k in keys_in(sys.stdin.read()) if k not in found]
    return found


def targets(
    client: JiraClient,
    keys: list[str] | None = None,
    jql: str | None = None,
    filter_id: str | None = None,
    from_file: Path | None = None,
    limit: int | None = None,
) -> list[str]:
    """Return the issue keys picked by keys ('-' reads stdin), --jql, --filter, --from-file.

    Keys read from stdin may be none at all (an empty search upstream): that picks nothing.
    """
    found = given(keys)
    if from_file:
        found += [k for k in read_keys_file(from_file) if k not in found]
    queries = []
    if jql:
        queries.append(jql)
    if filter_id:
        queries.append(client.filter(filter_id)["jql"])
    for query in queries:
        for issue in client.search(query, ["key"], limit=limit):
            if issue["key"] not in found:
                found.append(issue["key"])
    piped = STDIN in (keys or []) or (from_file is not None and str(from_file) == STDIN)
    if not found and not (jql or filter_id or piped):
        raise ResolveError(
            "say which issues: give keys, '-' for stdin, --jql, --filter or --from-file"
        )
    for key in found:
        if not KEY_RE.match(key) and not key.isdigit():
            raise ResolveError(f"{key!r} is not an issue key (like DEMO-12) or id")
    return found


# ── people ───────────────────────────────────────────────────────────────────


def looks_like_account_id(value: str) -> bool:
    """Return whether `value` is shaped like an Atlassian account id."""
    return bool(ACCOUNT_ID_RE.match(value))


def user(client: JiraClient, who: str, my_account_id: str | None = None) -> dict:
    """Return the one user `who` names: @me, an account id, an email, or part of a name."""
    who = who.strip()
    if who.lower() in ME:
        return client.myself() if not my_account_id else {"accountId": my_account_id}
    if looks_like_account_id(who):
        return {"accountId": who}
    found = list(client.get(f"{API}/user/search", query=who, maxResults=20) or [])
    humans = [u for u in found if u.get("accountType", "atlassian") == "atlassian"] or found
    exact = [
        u
        for u in humans
        if who.lower() in (u.get("emailAddress", "").lower(), u.get("displayName", "").lower())
    ]
    matches = exact or humans
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ResolveError(f"no user matches {who!r}; try their email or account id")
    names = ", ".join(u.get("displayName", "?") for u in matches[:8])
    raise ResolveError(f"{who!r} matches several people ({names}); use an email or account id")


def account_id(client: JiraClient, who: str, my_account_id: str | None = None) -> str | None:
    """Resolve an assignee-like value: None to clear it, '-1' for the project default."""
    lowered = who.strip().lower()
    if lowered in NOBODY:
        return None
    if lowered == DEFAULT:
        return "-1"
    return user(client, who, my_account_id)["accountId"]


# ── fields ───────────────────────────────────────────────────────────────────


@dataclass
class FieldCatalog:
    """The site's fields, looked up by id, key or (case-insensitive) name."""

    fields: list[dict]

    @classmethod
    def load(cls, client: JiraClient) -> FieldCatalog:
        """Read every field from the site."""
        return cls(client.fields())

    def find(self, name: str) -> dict:
        """Return the field called `name` (id, key, `cf[123]` or display name)."""
        wanted = name.strip()
        if m := re.fullmatch(r"cf\[(\d+)\]", wanted):
            wanted = f"customfield_{m.group(1)}"
        for field in self.fields:
            if wanted in (field.get("id"), field.get("key")):
                return field
        lowered = wanted.lower()
        named = [f for f in self.fields if f.get("name", "").lower() == lowered]
        if len(named) == 1:
            return named[0]
        if len(named) > 1:
            ids = ", ".join(f["id"] for f in named)
            raise ResolveError(f"several fields are called {name!r} ({ids}); use the id")
        close = [f["name"] for f in self.fields if lowered in f.get("name", "").lower()][:6]
        hint = f" Did you mean: {', '.join(close)}?" if close else " See `acli-py field list`."
        raise ResolveError(f"no field called {name!r}.{hint}")


def parse_assignment(text: str) -> tuple[str, str, bool]:
    """Split `NAME=VALUE` (coerced) or `NAME:=JSON` (raw) into (name, value, raw)."""
    eq = text.find("=")
    if eq <= 0:
        raise ResolveError(f"expected NAME=VALUE or NAME:=JSON, got {text!r}")
    raw = text[eq - 1] == ":"
    name = text[: eq - 1] if raw else text[:eq]
    return name.strip(), text[eq + 1 :], raw


def field_value(
    client: JiraClient, field: dict, value: str, my_account_id: str | None = None
) -> Any:
    """Convert a typed value to what the field's schema expects."""
    schema = field.get("schema") or {}
    kind = schema.get("type")
    items = schema.get("items")
    custom = schema.get("custom", "")
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if kind == "number":
        try:
            number = float(value)
        except ValueError as error:
            raise ResolveError(f"{field['name']} takes a number, got {value!r}") from error
        return int(number) if number.is_integer() else number
    if kind == "string":
        return adf.to_adf(value) if custom.endswith(":textarea") else value
    if kind == "option":
        return {"value": value}
    if kind == "option-with-child":
        parent, _, child = value.partition(">")
        option: dict[str, Any] = {"value": parent.strip()}
        if child.strip():
            option["child"] = {"value": child.strip()}
        return option
    if kind == "user":
        return {"accountId": account_id(client, value, my_account_id)}
    if kind in ("priority", "resolution", "issuetype", "securitylevel"):
        return {"id": value} if value.isdigit() else {"name": value}
    if kind in ("version", "component"):
        return {"name": value}
    if kind == "project":
        return {"key": value.upper()}
    if kind == "array":
        if items == "option":
            return [{"value": p} for p in parts]
        if items == "user":
            return [{"accountId": account_id(client, p, my_account_id)} for p in parts]
        if items in ("version", "component"):
            return [{"name": p} for p in parts]
        if items == "json" and custom.endswith(":gh-sprint"):
            return int(value)
        return parts
    if kind == "sd-customerrequesttype" or kind is None:
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def field_values(
    client: JiraClient,
    assignments: list[str],
    my_account_id: str | None = None,
    catalog: FieldCatalog | None = None,
) -> dict[str, Any]:
    """Resolve every --field NAME=VALUE / NAME:=JSON into {field id: value}."""
    if not assignments:
        return {}
    catalog = catalog or FieldCatalog.load(client)
    result: dict[str, Any] = {}
    for text in assignments:
        name, value, raw = parse_assignment(text)
        field = catalog.find(name)
        if raw:
            try:
                result[field["id"]] = json.loads(value)
            except ValueError as error:
                raise ResolveError(f"{name}:= needs valid JSON: {error}") from error
        else:
            result[field["id"]] = field_value(client, field, value, my_account_id)
    return result


# ── rich text ────────────────────────────────────────────────────────────────


def read_text_arg(text: str | None, file: Path | None) -> str | None:
    """Return text from an option, a file, or stdin when either is '-'."""
    import sys

    if text is not None and file is not None:
        raise ResolveError("give the text inline or as a file, not both")
    if text == "-" or (file is not None and str(file) == "-"):
        return sys.stdin.read()
    if file is not None:
        return file.read_text(encoding="utf-8")
    return text
