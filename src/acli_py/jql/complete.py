"""Suggest what comes next in a JQL or smart query, wherever the cursor is.

`Completer.complete(text, cursor)` works out what is being typed — a field, an operator, a
value, a list, an ORDER BY; or a smart filter such as `s:` or `@` — and returns ranked
suggestions with the span of text they replace. It is shared by the TUI, the shell and shell
completion, and knows nothing about any of them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from acli_py.jql import smart
from acli_py.jql.catalog import Catalog, FieldRef, Value, matches
from acli_py.jql.lexer import Kind, Token, quote, tokenize

LIMIT = 40

LIST_OPS = ("in", "not in", "was in", "was not in")
EMPTY_OPS = ("is", "is not")
PREDICATES = ("after", "before", "on", "during", "by", "from", "to")
DATE_VALUES = (
    ("-1d", "in the last day"),
    ("-7d", "in the last week"),
    ("-30d", "in the last 30 days"),
    ("startOfDay()", "today"),
    ("startOfWeek()", "this week"),
    ("startOfMonth()", "this month"),
    ("now()", "right now"),
)
SMART_DATES = (
    ("1d", "in the last day"),
    ("7d", "in the last week"),
    ("30d", "in the last 30 days"),
    (">30d", "more than 30 days ago"),
    ("today", "today"),
    ("week", "this week"),
    ("month", "this month"),
    ("none", "not set"),
)
DATE_FIELDS = {"created", "updated", "resolved", "due", "duedate", "lastviewed", "resolutiondate"}
ISSUE_FIELDS = {"key", "issue", "issuekey", "parent", "id"}


@dataclass(frozen=True)
class Suggestion:
    """One thing to insert."""

    text: str  # what replaces the span
    display: str  # what the list shows
    meta: str = ""  # a hint shown beside it
    kind: str = ""  # field | operator | value | function | keyword | filter | flag | issue


@dataclass
class Completion:
    """Suggestions for the span `text[start:end]`."""

    start: int
    end: int
    items: list[Suggestion] = field(default_factory=list)
    context: str = ""  # what is being typed, e.g. "value of status"
    mode: str = "smart"

    def apply(self, text: str, item: Suggestion) -> tuple[str, int]:
        """Return the text with `item` inserted, and where the cursor goes."""
        new = text[: self.start] + item.text + text[self.end :]
        return new, self.start + len(item.text)


def rank(items: list[Suggestion], prefix: str, limit: int = LIMIT) -> list[Suggestion]:
    """Keep the items matching `prefix`: prefix matches first, then word starts, then others."""
    if not prefix:
        return _unique(items)[:limit]
    low = prefix.lower().lstrip("\"'")
    scored = []
    for index, item in enumerate(items):
        name = item.display.lower()
        value = item.text.lower().strip("\"'")
        if name.startswith(low) or value.startswith(low):
            score = 0
        elif matches(item.display, low) or matches(item.meta, low):
            score = 1
        elif low in name or low in value:
            score = 2
        else:
            continue
        scored.append((score, index, item))
    scored.sort(key=lambda s: (s[0], s[1]))
    return _unique([s[2] for s in scored])[:limit]


def _unique(items: list[Suggestion]) -> list[Suggestion]:
    seen: set[tuple[str, str]] = set()
    result = []
    for item in items:
        key = (item.text.lower(), item.kind)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


class State(Enum):
    """Where the cursor is in a JQL query."""

    FIELD = "field"
    OPERATOR = "operator"
    VALUE = "value"
    LIST_VALUE = "list value"
    LIST_NEXT = "list separator"
    AFTER = "after a clause"
    ORDER_BY = "order by"
    ORDER_FIELD = "order field"
    ORDER_DIR = "order direction"


@dataclass
class JqlContext:
    """The result of reading the JQL before the cursor."""

    state: State = State.FIELD
    field: str = ""
    operator: str = ""
    depth: int = 0
    predicate: str = ""
    valid: bool = True  # False once a token appeared where JQL can't have one


def read_context(tokens: list[Token]) -> JqlContext:
    """Walk complete tokens and return where the next one would go."""
    ctx = JqlContext()
    func_depth = 0
    resume = State.AFTER
    prev: Token | None = None
    for tok in tokens:
        if func_depth:
            if tok.kind is Kind.LPAREN:
                func_depth += 1
            elif tok.kind is Kind.RPAREN:
                func_depth -= 1
                if not func_depth:
                    ctx.state = resume
            prev = tok
            continue
        state = ctx.state
        called = (
            tok.kind is Kind.LPAREN
            and prev is not None
            and prev.kind is Kind.WORD
            and prev.end == tok.start
        )
        if called and state in (State.AFTER, State.LIST_NEXT):
            func_depth, resume = 1, state
        elif state is State.FIELD:
            if tok.kind is Kind.LPAREN:
                ctx.depth += 1
            elif tok.kind in (Kind.WORD, Kind.STRING) and not tok.is_word("not"):
                ctx.field, ctx.operator, ctx.predicate = tok.value, "", ""
                ctx.state = State.OPERATOR
        elif state is State.OPERATOR:
            ctx = _read_operator(ctx, tok)
        elif state is State.VALUE:
            if tok.kind is Kind.LPAREN:
                ctx.state = State.LIST_VALUE
            elif tok.is_word("not") and ctx.operator in ("is", "was", "was in"):
                ctx.operator = ctx.operator.replace("was in", "was") + " not"
            elif tok.is_word("in") and ctx.operator in ("was", "was not"):
                ctx.operator += " in"
            elif tok.kind in (Kind.WORD, Kind.STRING):
                ctx.state = State.AFTER
        elif state is State.LIST_VALUE:
            if tok.kind is Kind.RPAREN:
                ctx.state = State.AFTER
            elif tok.kind in (Kind.WORD, Kind.STRING):
                ctx.state = State.LIST_NEXT
        elif state is State.LIST_NEXT:
            if tok.kind is Kind.COMMA:
                ctx.state = State.LIST_VALUE
            elif tok.kind is Kind.RPAREN:
                ctx.state = State.AFTER
        elif state is State.AFTER:
            if tok.is_word("and", "or"):
                ctx.state = State.FIELD
            elif tok.is_word("order"):
                ctx.state = State.ORDER_BY
            elif tok.kind is Kind.RPAREN:
                ctx.depth = max(0, ctx.depth - 1)
            elif tok.is_word(*PREDICATES) and ctx.operator.startswith(("was", "changed")):
                ctx.predicate = tok.text.lower()
                ctx.state = State.VALUE
        elif state is State.ORDER_BY:
            if tok.is_word("by"):
                ctx.state = State.ORDER_FIELD
        elif state is State.ORDER_FIELD:
            if tok.kind in (Kind.WORD, Kind.STRING):
                ctx.state = State.ORDER_DIR
        elif state is State.ORDER_DIR and tok.kind is Kind.COMMA:
            ctx.state = State.ORDER_FIELD
        prev = tok
    return ctx


def _read_operator(ctx: JqlContext, tok: Token) -> JqlContext:
    if tok.kind is Kind.OP:
        ctx.operator = tok.text
        ctx.state = State.VALUE
    elif tok.is_word("changed"):
        ctx.operator = "changed"
        ctx.state = State.AFTER
    elif tok.is_word("in"):
        ctx.operator = (ctx.operator + " in").strip()
        ctx.state = State.VALUE
    elif tok.is_word("not"):
        ctx.operator = "not"
    elif tok.is_word("is", "was"):
        ctx.operator = tok.text.lower()
        ctx.state = State.VALUE
    else:
        ctx.valid = False
    return ctx


class Completer:
    """Completes JQL and smart queries from a catalog."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    # ── entry point ──────────────────────────────────────────────────────────

    def complete(self, text: str, cursor: int | None = None, *, mode: str = "auto") -> Completion:
        """Return suggestions for the text at `cursor` (default: the end)."""
        cursor = len(text) if cursor is None else max(0, min(cursor, len(text)))
        if mode == "auto":
            if smart.looks_like_jql(text):
                mode = "jql"
            elif self._starts_jql(text[:cursor]):
                # "status " begins JQL; "status report" was text after all.
                found = self.complete_jql(text, cursor)
                return found if found.items else self.complete_smart(text, cursor)
            else:
                mode = "smart"
        if mode == "jql":
            return self.complete_jql(text, cursor)
        return self.complete_smart(text, cursor)

    def _starts_jql(self, text: str) -> bool:
        """Return whether `text` starts a JQL clause: a known field, then more than a word."""
        tokens = tokenize(text)
        if tokens and not text[-1:].isspace():
            tokens.pop()  # the word being typed
        if not tokens:
            return False
        first = tokens[0]
        if first.kind is Kind.WORD and ":" in first.text:
            return False
        if first.is_word("not") or first.kind is Kind.LPAREN:
            return True
        ctx = read_context(tokens)
        return (
            self.field_ref(first.value) is not None and ctx.valid and ctx.state is not State.FIELD
        )

    # ── JQL ──────────────────────────────────────────────────────────────────

    def field_ref(self, name: str) -> FieldRef | None:
        """Return the catalog's field called `name` (any case), if there is one."""
        low = name.lower()
        return next(
            (f for f in self.catalog.fields() if low in (f.name.lower(), f.display.lower())),
            None,
        )

    def complete_jql(self, text: str, cursor: int) -> Completion:
        """Complete JQL."""
        tokens = list(tokenize(text[:cursor]))
        partial: Token | None = None
        if (
            tokens
            and tokens[-1].end == cursor
            and (
                tokens[-1].kind is Kind.WORD
                or (tokens[-1].kind is Kind.STRING and not tokens[-1].closed)
            )
        ):
            partial = tokens.pop()
        ctx = read_context(tokens)
        prefix = partial.value if partial else ""
        start = partial.start if partial else cursor
        end = _token_end(text, start, cursor) if partial else cursor
        items = self._jql_items(ctx, prefix)
        # A word may also finish the clause before it: "status = Done an" → AND.
        return Completion(start, end, rank(items, prefix), _describe(ctx), "jql")

    def _jql_items(self, ctx: JqlContext, prefix: str) -> list[Suggestion]:
        state = ctx.state
        if state is State.FIELD:
            items = [
                Suggestion(
                    quote(f.name) + " ",
                    f.name,
                    f.display if f.display != f.name else ("custom field" if f.custom else ""),
                    "field",
                )
                for f in self.catalog.fields()
            ]
            return [*items, Suggestion("NOT ", "NOT", "negate the next clause", "keyword")]
        if state is State.OPERATOR:
            if ctx.operator == "not":
                return [Suggestion("in ", "in", "not in a list", "operator")]
            ref = self.field_ref(ctx.field)
            ops = ref.operators if ref else ("=", "!=", "in", "not in", "is", "is not", "~")
            return [Suggestion(op + " ", op, _OP_HELP.get(op, ""), "operator") for op in ops]
        if state in (State.VALUE, State.LIST_VALUE):
            return self._value_items(ctx, prefix, in_list=state is State.LIST_VALUE)
        if state is State.LIST_NEXT:
            return [
                Suggestion(", ", ",", "another value", "keyword"),
                Suggestion(") ", ")", "close the list", "keyword"),
            ]
        if state is State.AFTER:
            items = [
                Suggestion("AND ", "AND", "both must match", "keyword"),
                Suggestion("OR ", "OR", "either may match", "keyword"),
                Suggestion("ORDER BY ", "ORDER BY", "sort the results", "keyword"),
            ]
            if ctx.depth:
                items.insert(0, Suggestion(") ", ")", "close the group", "keyword"))
            if ctx.operator.startswith(("was", "changed")):
                items += [
                    Suggestion(p.upper() + " ", p.upper(), "history predicate", "keyword")
                    for p in PREDICATES
                ]
            return items
        if state is State.ORDER_BY:
            return [Suggestion("BY ", "BY", "", "keyword")]
        if state is State.ORDER_FIELD:
            return [
                Suggestion(
                    quote(f.name) + " ", f.name, f.display if f.display != f.name else "", "field"
                )
                for f in self.catalog.fields()
                if f.orderable
            ]
        return [
            Suggestion("ASC", "ASC", "smallest first", "keyword"),
            Suggestion("DESC", "DESC", "largest or newest first", "keyword"),
            Suggestion(", ", ",", "sort by another field too", "keyword"),
        ]

    def _value_items(self, ctx: JqlContext, prefix: str, *, in_list: bool) -> list[Suggestion]:
        op = ctx.operator
        field_name = ctx.field
        tail = "" if in_list else " "
        if op in EMPTY_OPS or op in ("was", "was not"):
            empties = [Suggestion("EMPTY ", "EMPTY", "no value", "keyword")]
            if op in ("is", "was"):
                empties.append(Suggestion("not ", "not", "", "keyword"))
            if op in EMPTY_OPS:
                return empties
            if op == "was":
                empties.append(Suggestion("in ", "in", "", "keyword"))
        else:
            empties = []
        if op in LIST_OPS and not in_list:
            functions = [
                Suggestion(f.name + " ", f.name, "function", "function")
                for f in self.catalog.functions()
                if f.is_list
            ]
            opener = Suggestion("(", "(", "a list of values", "keyword")
            values = [
                Suggestion("(" + quote(v.value), v.value, v.display, "value")
                for v in self._values(field_name, prefix)
            ]
            return [opener, *values, *functions]
        items = [
            Suggestion(
                quote(v.value) + tail, v.value, v.display if v.display != v.value else "", "value"
            )
            for v in self._values(field_name, prefix)
        ]
        if field_name.lower() in DATE_FIELDS:
            items += [Suggestion(v + tail, v, hint, "value") for v, hint in DATE_VALUES]
        items += [
            Suggestion(f.name + tail, f.name, "function", "function")
            for f in self.catalog.functions()
            if in_list or not f.is_list or op in LIST_OPS
        ]
        return [*empties, *items]

    def _values(self, field_name: str, prefix: str) -> list[Value]:
        if not field_name:
            return []
        if field_name.lower() in ISSUE_FIELDS:
            return self.catalog.issues(prefix)
        return self.catalog.values(field_name, prefix)

    # ── smart ────────────────────────────────────────────────────────────────

    def complete_smart(self, text: str, cursor: int) -> Completion:
        """Complete a smart query."""
        start = cursor
        for term in smart.terms(text[:cursor]):
            if term.end == cursor:
                start = term.start
        end = _token_end(text, start, cursor) if start < cursor else cursor
        partial = text[start:cursor]
        negated = partial.startswith("-") and len(partial) > 1
        sign = "-" if negated else ""
        body = partial[1:] if negated else partial
        items, context = self._smart_items(body, sign)
        prefix = _smart_prefix(body)
        return Completion(start, end, rank(items, prefix), context, "smart")

    def _smart_items(self, body: str, sign: str) -> tuple[list[Suggestion], str]:
        if body[:1] in smart.SIGILS:
            spec = smart.lookup(smart.SIGILS[body[0]])
            assert spec is not None
            value = smart.unquote(body[1:])
            return self._smart_values(spec, value, f"{sign}{body[0]}"), f"value of {spec.name}"
        match = re.match(r"^([A-Za-z]+):(.*)$", body, re.S)
        if match and (spec := smart.lookup(match.group(1))):
            head = f"{sign}{match.group(1)}:"
            return self._smart_values(spec, smart.unquote(match.group(2)), head), (
                f"value of {spec.name}"
            )
        items = [
            Suggestion(f"{sign}{spec.name}:", f"{spec.name}:", spec.help, "filter")
            for spec in smart.FILTERS
        ]
        items += [
            Suggestion(f"{sign}{alias}:", f"{alias}:", f"= {spec.name}:", "filter")
            for spec in smart.FILTERS
            for alias in spec.aliases
        ]
        items += [
            Suggestion(f"{sign}is:{flag} ", f"is:{flag}", hint, "flag")
            for flag, (_, hint) in smart.FLAGS.items()
        ]
        items += [
            Suggestion(f"{sign}@", "@", "assignee", "filter"),
            Suggestion(f"{sign}#", "#", "label", "filter"),
            Suggestion(f"{sign}!", "!", "priority", "filter"),
        ]
        if re.match(r"^[A-Za-z][A-Za-z0-9_]*-\d*$", body):
            items = [
                Suggestion(f"{sign}{v.value} ", v.value, v.display, "issue")
                for v in self.catalog.issues(body)
            ] + items
        if body and not sign:
            # Plain JQL fields too, for switching to JQL: "project" → "project = …".
            items += [
                Suggestion(quote(f.name) + " ", f.name, "JQL field", "field")
                for f in self.catalog.fields()
            ]
        return items, "filter or text"

    def _smart_values(self, spec: smart.Filter, value: str, head: str) -> list[Suggestion]:
        # Lists: complete the last comma-separated part, keep the others.
        kept, last = "", value
        if spec.kind in ("value", "user", "sprint", "sort") and "," in value:
            kept, _, last = value.rpartition(",")
            kept += ","
        pairs: list[tuple[str, str]] = []
        if spec.kind == "flag":
            pairs = [(flag, hint) for flag, (_, hint) in smart.FLAGS.items()]
        elif spec.kind == "date":
            pairs = list(SMART_DATES)
        elif spec.kind == "sort":
            fields = [f.name for f in self.catalog.fields() if f.orderable]
            names = ["updated", "created", "priority", "key", "status", "due", "rank", *fields]
            pairs = [(n, "ascending") for n in names] + [(f"-{n}", "descending") for n in names]
        elif spec.kind in ("user", "sprint", "value"):
            if spec.kind == "user":
                pairs += [("me", "you"), ("none", "nobody")]
            if spec.kind == "sprint":
                pairs += [
                    ("current", "active sprints"),
                    ("future", "future sprints"),
                    ("closed", "closed sprints"),
                ]
            found = (
                self.catalog.issues(last)
                if spec.jql_field in ISSUE_FIELDS
                else self.catalog.values(spec.jql_field, last)
            )
            pairs += [(v.value, v.display if v.display != v.value else "") for v in found]
        close = "" if spec.kind == "sort" else " "
        return [
            Suggestion(f"{head}{kept}{_smart_quote(v)}{close}", v, hint, "value")
            for v, hint in pairs
        ]


_OP_HELP = {
    "=": "equals",
    "!=": "does not equal",
    "~": "contains text",
    "!~": "does not contain text",
    ">": "greater than",
    ">=": "at least",
    "<": "less than",
    "<=": "at most",
    "in": "one of a list",
    "not in": "none of a list",
    "is": "is EMPTY",
    "is not": "is not EMPTY",
    "was": "had this value",
    "was in": "had one of these values",
    "was not": "never had this value",
    "was not in": "never had any of these",
    "changed": "changed at some point",
}


def _smart_quote(value: str) -> str:
    return f'"{value}"' if re.search(r"[\s,\"']", value) else value


def _smart_prefix(body: str) -> str:
    """Return the part of a smart term that suggestions are matched against."""
    if body[:1] in smart.SIGILS:
        body = body[1:]
    elif match := re.match(r"^[A-Za-z]+:(.*)$", body, re.S):
        body = match.group(1)
    else:
        return body
    return smart.unquote(body.rpartition(",")[2])


def _token_end(text: str, start: int, cursor: int) -> int:
    """Return where the token around the cursor ends (the rest of a word being edited)."""
    end = cursor
    while end < len(text) and not text[end].isspace() and text[end] not in "(),=~<>!":
        end += 1
    return end if start < cursor else cursor


def _describe(ctx: JqlContext) -> str:
    if ctx.state in (State.VALUE, State.LIST_VALUE):
        return f"value of {ctx.field}"
    if ctx.state is State.OPERATOR:
        return f"operator for {ctx.field}"
    return ctx.state.value
