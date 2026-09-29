"""Smart queries: a short, forgiving search syntax that compiles to JQL.

    @me #web s:progress is:open updated:7d "login fails" sort:-priority

reads as "assigned to me, labelled web, status In Progress, not done, updated in the last week,
mentioning 'login fails', highest priority first". Every term is optional and they combine
with AND; the same filter given twice means either (`s:todo s:review`), and a leading `-`
negates a term (`-#legacy`). Words that aren't filters are searched as text, and issue keys
(`DEMO-12`) are picked directly. Anything that already looks like JQL is passed through.

`cheatsheet()` lists every term; `aj issue search --syntax` prints it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from acli_py.jql.lexer import quote


@dataclass(frozen=True)
class Filter:
    """A `name:value` term."""

    name: str
    jql_field: str
    help: str
    aliases: tuple[str, ...] = ()
    kind: str = "value"  # value | user | date | text | sprint | sort | flag | raw
    example: str = ""


FILTERS = (
    Filter("project", "project", "Project key", ("p", "proj"), example="p:DEMO"),
    Filter("status", "status", "Status name", ("s", "st"), example='s:"In Progress"'),
    Filter("type", "issuetype", "Issue type", ("t",), example="t:bug"),
    Filter("assignee", "assignee", "Assignee (@me, none, name, email)", ("a",), "user", "a:bob"),
    Filter("reporter", "reporter", "Reporter", ("r", "by"), "user", "r:@me"),
    Filter("label", "labels", "Label", ("l",), example="l:web"),
    Filter("priority", "priority", "Priority", ("pr", "prio"), example="pr:high"),
    Filter("component", "component", "Component", ("c", "comp"), example="c:api"),
    Filter("version", "fixVersion", "Fix version", ("v", "fix"), example="v:2.1"),
    Filter(
        "sprint",
        "sprint",
        "Sprint: current, future, closed, id or name",
        (),
        "sprint",
        "sprint:current",
    ),
    Filter("parent", "parent", "Parent or epic key", ("epic",), example="parent:DEMO-1"),
    Filter("resolution", "resolution", "Resolution", ("res",), example="res:done"),
    Filter("watcher", "watcher", "Watched by", ("w",), "user", "w:@me"),
    Filter(
        "created", "created", "Created: 7d, >30d, today, 2026-09-01, A..B", (), "date", "created:7d"
    ),
    Filter(
        "updated", "updated", "Updated: 7d (last week), >30d (older)", ("u",), "date", "updated:2d"
    ),
    Filter("resolved", "resolved", "Resolved", (), "date", "resolved:week"),
    Filter("due", "duedate", "Due: 3d (within 3 days), >2w, today, a date", (), "date", "due:3d"),
    Filter("text", "text", "Full-text search", ("q",), "text", 'q:"login fails"'),
    Filter("summary", "summary", "Search the summary only", ("title",), "text", "summary:crash"),
    Filter("key", "key", "Issue key", ("k",), example="key:DEMO-1"),
    Filter("filter", "filter", "A saved filter's id or name", ("f",), example="filter:10042"),
    Filter(
        "is",
        "",
        "open, done, todo, wip, mine, unassigned, reported, watching, overdue, "
        "sprint, backlog, recent, flagged, epic, subtask",
        (),
        "flag",
        "is:open",
    ),
    Filter(
        "sort",
        "",
        "Order: field names, '-' for descending",
        ("order", "o"),
        "sort",
        "sort:-priority,key",
    ),
    Filter("jql", "", "Raw JQL for one clause", (), "raw", 'jql:"cf[10016] > 3"'),
)
SIGILS = {"@": "assignee", "#": "label", "!": "priority"}

FLAGS: dict[str, tuple[str, str]] = {
    "open": ("statusCategory != Done", "not done yet"),
    "done": ("statusCategory = Done", "done"),
    "closed": ("statusCategory = Done", "done"),
    "todo": ('statusCategory = "To Do"', "not started"),
    "wip": ('statusCategory = "In Progress"', "in progress"),
    "mine": ("assignee = currentUser()", "assigned to me"),
    "unassigned": ("assignee is EMPTY", "nobody assigned"),
    "reported": ("reporter = currentUser()", "reported by me"),
    "watching": ("watcher = currentUser()", "watched by me"),
    "overdue": (
        "duedate < startOfDay() AND statusCategory != Done",
        "past the due date and not done",
    ),
    "sprint": ("sprint in openSprints()", "in an active sprint"),
    "backlog": ("sprint is EMPTY AND statusCategory != Done", "in no sprint, not done"),
    "recent": ("updated >= -7d", "updated this week"),
    "flagged": ("flagged is not EMPTY", "flagged as impediment"),
    "epic": ("issuetype = Epic", "epics"),
    "subtask": ("issuetype in subTaskIssueTypes()", "subtasks"),
}
SORT_ALIASES = {
    "type": "issuetype",
    "due": "duedate",
    "prio": "priority",
    "pr": "priority",
    "version": "fixVersion",
    "points": "Story point estimate",
}
USER_WORDS = {
    "me": "currentUser()",
    "@me": "currentUser()",
    "none": "EMPTY",
    "unassigned": "EMPTY",
    "nobody": "EMPTY",
}
DEFAULT_ORDER = "updated DESC"

_BY_NAME = {name: f for f in FILTERS for name in (f.name, *f.aliases)}
_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]+-\d+$")
_REL = re.compile(r"^([<>]?)(-?\d+)([mhdwMy])$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# JQL operators outside quotes and not right after a `name:` (where `<`/`>` are smart syntax).
_JQL = re.compile(
    r"""(?ix)
    (?<!:)(?:!=|!~|>=|<=|=|~)           # an operator, not glued to a smart `name:`
    | \s(?:!=|!~|>=|<=|[=~<>])\s        # a spaced operator
    | \border\s+by\b
    | \b(?:not\s+)?in\s*(?:\w+\s*)?\(
    | \bis\s+(?:not\s+)?(?:empty|null)\b
    """
)


def lookup(name: str) -> Filter | None:
    """Return the filter called `name` (or one of its aliases)."""
    return _BY_NAME.get(name.lower())


def _outside_quotes(text: str) -> str:
    return re.sub(r'"(?:\\.|[^"\\])*"?|\'(?:\\.|[^\'\\])*\'?', '""', text)


def looks_like_jql(text: str) -> bool:
    """Return whether `text` is JQL rather than a smart query."""
    return bool(_JQL.search(_outside_quotes(text)))


# ── splitting ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Term:
    """One whitespace-separated piece of a smart query, as typed."""

    text: str
    start: int
    end: int

    @property
    def negated(self) -> bool:
        """Return whether the term starts with '-' (and is more than a dash)."""
        return self.text.startswith("-") and len(self.text) > 1

    @property
    def body(self) -> str:
        """Return the term without its leading '-'."""
        return self.text[1:] if self.negated else self.text

    def split(self) -> tuple[str | None, str]:
        """Return (filter name or sigil, value), e.g. ('s', 'In Progress') or ('@', 'bob')."""
        body = self.body
        if body[:1] in SIGILS:
            return body[0], unquote(body[1:])
        match = re.match(r"^([A-Za-z]+):(.*)$", body, re.S)
        if match:
            return match.group(1).lower(), unquote(match.group(2))
        return None, unquote(body)


def unquote(value: str) -> str:
    """Remove one level of quotes (closed or not) from `value`."""
    if value[:1] in "\"'":
        inner = value[1:-1] if len(value) > 1 and value[-1] == value[0] else value[1:]
        return re.sub(r"\\(.)", r"\1", inner)
    return value


def terms(text: str) -> list[Term]:
    """Split a smart query into terms; quotes keep spaces inside a term."""
    found: list[Term] = []
    i, n = 0, len(text)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        start, quote_char = i, ""
        while i < n and (quote_char or not text[i].isspace()):
            char = text[i]
            if quote_char:
                if char == "\\":
                    i += 1
                elif char == quote_char:
                    quote_char = ""
            elif char in "\"'":
                quote_char = char
            i += 1
        found.append(Term(text[start:i], start, i))
    return found


# ── compiling ────────────────────────────────────────────────────────────────

Resolver = Callable[[str, str], str]
"""Turns a typed value into the site's spelling: (jql field, typed) -> value."""


@dataclass
class Compiled:
    """A query ready for Jira."""

    where: str
    order: str
    mode: str  # "smart" or "jql"
    warnings: list[str] = field(default_factory=list)

    @property
    def jql(self) -> str:
        """Return the full JQL."""
        tail = f" ORDER BY {self.order}" if self.order else ""
        return f"{self.where}{tail}".strip()


def _relative(field_name: str, sign: str, amount: str, unit: str) -> str:
    unit = {"M": "w", "y": "w"}.get(unit, unit)  # JQL has no months or years: use weeks
    number = int(amount)
    if field_name == "duedate":
        if sign == ">":
            return f"duedate > {number}{unit}"
        return f"duedate <= {number}{unit}"
    if sign == ">":
        return f"{field_name} <= -{abs(number)}{unit}"
    return f"{field_name} >= -{abs(number)}{unit}"


def date_clause(field_name: str, value: str) -> str:
    """Return the JQL for a date filter such as `updated:7d`."""
    value = value.strip()
    low = value.lower()
    if low in ("none", "empty"):
        return f"{field_name} is EMPTY"
    starts = {
        "today": "startOfDay()",
        "yesterday": "startOfDay(-1)",
        "week": "startOfWeek()",
        "month": "startOfMonth()",
        "year": "startOfYear()",
    }
    if low in starts:
        if field_name == "duedate":
            ends = {
                "today": "endOfDay()",
                "yesterday": "endOfDay(-1)",
                "week": "endOfWeek()",
                "month": "endOfMonth()",
                "year": "endOfYear()",
            }
            return f"duedate <= {ends[low]}"
        return f"{field_name} >= {starts[low]}"
    if match := _REL.match(value):
        return _relative(field_name, *match.groups())
    if ".." in value:
        first, _, last = value.partition("..")
        parts = []
        if first:
            parts.append(f'{field_name} >= "{first}"')
        if last:
            end = last
            if _DAY.match(last):
                end = (date.fromisoformat(last) + timedelta(days=1)).isoformat()
                parts.append(f'{field_name} < "{end}"')
            else:
                parts.append(f'{field_name} <= "{last}"')
        return " AND ".join(parts)
    if value[:1] in "<>":
        return f'{field_name} {value[0]} "{value[1:]}"'
    if _DAY.match(value):
        after = (date.fromisoformat(value) + timedelta(days=1)).isoformat()
        return f'{field_name} >= "{value}" AND {field_name} < "{after}"'
    raise ValueError(
        f"{field_name}: can't read {value!r} as a date "
        "(try 7d, >30d, today, week, 2026-09-01 or 2026-09-01..2026-09-30)"
    )


def _user(value: str, fixed: Callable[[str, str], str], field_name: str) -> str:
    low = value.lower()
    if low in USER_WORDS:
        return USER_WORDS[low]
    return quote(fixed(field_name, value))


def _sprint(value: str) -> str:
    low = value.lower()
    named = {
        "current": "openSprints()",
        "open": "openSprints()",
        "active": "openSprints()",
        "future": "futureSprints()",
        "next": "futureSprints()",
        "closed": "closedSprints()",
        "none": "EMPTY",
    }
    return named.get(low) or (value if value.isdigit() else quote(value))


def _order(value: str, warnings: list[str]) -> str:
    parts = []
    for raw in value.split(","):
        name = raw.strip()
        if not name:
            continue
        direction = "DESC" if name.startswith("-") else "ASC"
        name = name.lstrip("+-")
        name = SORT_ALIASES.get(name.lower(), name)
        parts.append(f"{quote(name)} {direction}")
    if not parts:
        warnings.append("sort: give at least one field")
    return ", ".join(parts)


# Fields every issue has a value for. A negated filter on any other field also matches issues
# where it is empty: in JQL, `labels != legacy` alone silently drops the unlabelled issues.
ALWAYS_SET = {"project", "issuetype", "status", "key", "statusCategory"}


def _clause(field_name: str, values: list[str], negated: bool) -> str:
    empty = [v for v in values if v == "EMPTY"]
    rest = [v for v in values if v != "EMPTY"]
    if negated and rest and not empty and field_name not in ALWAYS_SET:
        op = "!=" if len(rest) == 1 else "not in"
        listed = rest[0] if len(rest) == 1 else f"({', '.join(rest)})"
        return f"({field_name} {op} {listed} OR {field_name} is EMPTY)"
    parts = []
    if rest:
        if len(rest) == 1:
            parts.append(f"{field_name} {'!=' if negated else '='} {rest[0]}")
        else:
            op = "not in" if negated else "in"
            parts.append(f"{field_name} {op} ({', '.join(rest)})")
    if empty:
        parts.append(f"{field_name} is {'not ' if negated else ''}EMPTY")
    joiner = " AND " if negated else " OR "
    text = joiner.join(parts)
    return f"({text})" if len(parts) > 1 else text


def compile_query(
    text: str,
    *,
    resolve: Resolver | None = None,
    default_order: str = DEFAULT_ORDER,
) -> Compiled:
    """Compile a smart query (or pass JQL through) into JQL.

    `resolve` fixes the spelling of names (`progress` → `"In Progress"`), when given.
    Raises ValueError for a term that can't be read, such as a bad date.
    """
    text = text.strip()
    if looks_like_jql(text):
        match = re.search(r"(?i)\border\s+by\b(.*)$", text)
        where = text[: match.start()].strip() if match else text
        order = match.group(1).strip() if match else ""
        return Compiled(where, order, "jql")

    warnings: list[str] = []
    grouped: dict[tuple[str, bool], list[str]] = {}
    clauses: list[str] = []
    words: list[str] = []
    keys: list[str] = []
    order = ""

    def add(field_name: str, value: str, negated: bool) -> None:
        values = grouped.setdefault((field_name, negated), [])
        if value not in values:
            values.append(value)

    def fixed(field_name: str, value: str) -> str:
        return resolve(field_name, value) if resolve else value

    for term in terms(text):
        name, value = term.split()
        negated = term.negated
        if name is None:
            if _KEY.match(value):
                if negated:
                    add("key", value.upper(), True)
                else:
                    keys.append(value.upper())
            elif negated:
                clauses.append(f"text !~ {quote(value)}")
            else:
                words.append(value)
            continue
        if name in SIGILS:
            name = SIGILS[name]
        spec = lookup(name)
        if spec is None:
            warnings.append(f"unknown filter {name}: (searched as text)")
            words.append(term.body)
            continue
        if not value and spec.kind != "sort":
            warnings.append(f"{spec.name}: needs a value, e.g. {spec.example}")
            continue
        for part in _values(value, spec.kind):
            clause = _term_clause(spec, part, negated, fixed, warnings, add)
            if clause == "__sort__":
                order = _order(value, warnings)
                break
            if clause:
                clauses.append(clause)

    if keys:
        clauses.insert(0, f"key = {keys[0]}" if len(keys) == 1 else f"key in ({', '.join(keys)})")
    for (field_name, negated), values in grouped.items():
        clauses.append(_clause(field_name, values, negated))
    if words:
        clauses.append(f"text ~ {quote(' '.join(words))}")
    return Compiled(" AND ".join(clauses), order or default_order, "smart", warnings)


def _values(value: str, kind: str) -> list[str]:
    """Split `a,b` into values, except where commas mean something else."""
    if kind in ("sort", "text", "raw", "date"):
        return [value]
    return [v.strip() for v in value.split(",") if v.strip()] or [value]


def _term_clause(
    spec: Filter,
    value: str,
    negated: bool,
    fixed: Callable[[str, str], str],
    warnings: list[str],
    add: Callable[[str, str, bool], None],
) -> str | None:
    """Return a clause for one term, or None after grouping its value with `add`."""
    not_ = "NOT " if negated else ""
    if spec.kind == "sort":
        return "__sort__"
    if spec.kind == "flag":
        flag = FLAGS.get(value.lower())
        if flag is None:
            warnings.append(f"is:{value}: unknown (try {', '.join(FLAGS)})")
            return None
        return f"{not_}({flag[0]})" if negated or " AND " in flag[0] else flag[0]
    if spec.kind == "raw":
        return f"{not_}({value})"
    if spec.kind == "text":
        return f"{spec.jql_field} {'!~' if negated else '~'} {quote(value)}"
    if spec.kind == "date":
        clause = date_clause(spec.jql_field, value)
        return f"NOT ({clause})" if negated else (f"({clause})" if " AND " in clause else clause)
    if spec.kind == "user":
        add(spec.jql_field, _user(value.lstrip("@"), fixed, spec.jql_field), negated)
        return None
    if spec.kind == "sprint":
        add(spec.jql_field, _sprint(value), negated)
        return None
    if spec.name == "filter":
        return f"{not_}filter = {value if value.isdigit() else quote(value)}"
    if spec.name in ("project", "key", "parent"):
        value = value.upper()
    if value.lower() in ("none", "empty"):
        add(spec.jql_field, "EMPTY", negated)
        return None
    add(spec.jql_field, quote(fixed(spec.jql_field, value)), negated)
    return None


def cheatsheet() -> list[tuple[str, str, str]]:
    """Return (term, aliases, meaning) rows describing the smart syntax."""
    rows = [
        ("@NAME", "assignee:", "Assigned to (@me, @none, a name or email)"),
        ("#LABEL", "label:", "Labelled"),
        ("!PRIORITY", "priority:", "With this priority"),
    ]
    for spec in FILTERS:
        aliases = ", ".join(f"{a}:" for a in spec.aliases)
        rows.append((f"{spec.name}:", aliases, f"{spec.help} — {spec.example}"))
    rows += [
        ("-TERM", "", "Negate a term: -#legacy, -s:done, -is:mine"),
        ("DEMO-12", "", "Pick issues by key"),
        ("words", "", 'Anything else is searched as text ("quote phrases")'),
    ]
    return rows
