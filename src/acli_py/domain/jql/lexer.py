"""Split JQL into tokens, keeping their positions, and tolerating half-typed input.

The lexer never fails: an unterminated string runs to the end of the text, and a stray
character becomes a one-character word. That is what completion needs, since it reads queries
while they are being typed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Kind(Enum):
    """What a token is."""

    WORD = "word"
    STRING = "string"
    OP = "op"
    LPAREN = "("
    RPAREN = ")"
    COMMA = ","


@dataclass(frozen=True)
class Token:
    """A piece of a query, with where it sits in the text."""

    kind: Kind
    text: str
    start: int
    end: int
    closed: bool = True  # False for a string still missing its closing quote

    @property
    def value(self) -> str:
        """Return the token's value: strings unquoted and unescaped."""
        if self.kind is not Kind.STRING:
            return self.text
        inner = self.text[1:-1] if self.closed else self.text[1:]
        return re.sub(r"\\(.)", r"\1", inner)

    def is_word(self, *words: str) -> bool:
        """Return whether this is one of `words`, ignoring case."""
        return self.kind is Kind.WORD and self.text.lower() in words


_OPS = ("!=", "!~", ">=", "<=", "=", "~", ">", "<")
# Characters that end a bare word. `-`, `.`, `@`, `[`, `]`, `/`, `:` stay inside words, so
# DEMO-12, cf[10016], 2026-09-01, -7d, user@example.com and 10:30 are one word each.
_BREAK = set(" \t\r\n()=,!~<>\"'")


def tokenize(text: str) -> list[Token]:
    """Return the tokens of `text`."""
    tokens: list[Token] = []
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char.isspace():
            i += 1
            continue
        if char in "\"'":
            j = i + 1
            while j < n and text[j] != char:
                j += 2 if text[j] == "\\" else 1
            closed = j < n
            end = min(j + 1, n)
            tokens.append(Token(Kind.STRING, text[i:end], i, end, closed))
            i = end
            continue
        if char in "(),":
            kind = {"(": Kind.LPAREN, ")": Kind.RPAREN, ",": Kind.COMMA}[char]
            tokens.append(Token(kind, char, i, i + 1))
            i += 1
            continue
        op = next((o for o in _OPS if text.startswith(o, i)), None)
        if op:
            tokens.append(Token(Kind.OP, op, i, i + len(op)))
            i += len(op)
            continue
        j = i + 1 if char == "!" else i
        while j < n and text[j] not in _BREAK:
            j += 1
        j = max(j, i + 1)
        tokens.append(Token(Kind.WORD, text[i:j], i, j))
        i = j
    return tokens


# Words JQL reserves: a value spelled like one must be quoted.
RESERVED = frozenset(
    """
    a an abort access add after alias alter and any are as asc audit avg before begin between
    boolean break by byte catch cf changed char character check checkpoint collate collation
    column commit connect continue count create current date decimal declare decrement default
    defaults define delete delimiter desc difference distinct divide do double drop else empty
    encoding end equals escape exclusive exec execute exists explain false fetch file field
    first float for from function go goto grant greater group having identified if immediate in
    increment index initial inner inout input insert int integer intersect intersection into is
    isempty isnull join last left less like limit lock long max min minus mode modify modulo
    more multiply next noaudit not notin nowait null number object of on option or order outer
    output power previous prior privileges public raise raw remainder rename resume return
    returns revoke right row rowid rownum rows select session set share size sqlexception start
    string subtract sum synonym table then to trans transaction trigger true uid union unique
    update user validate values view was when whenever where while with
    """.split()  # noqa: SIM905 - one word per slot would be 250 lines
)
_BARE = re.compile(r"^[A-Za-z0-9_.@\-\[\]]+$")


def quote(value: str) -> str:
    """Return `value` as a JQL literal: bare when that is safe, else double-quoted."""
    if value and _BARE.match(value) and value.lower() not in RESERVED:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
