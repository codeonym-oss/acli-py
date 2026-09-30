from __future__ import annotations

import re

from mediary.cqrs import query_handler

from acli_py.application.ports import IssueSearch
from acli_py.application.queries.compile_search.query import (
    ME,
    NOBODY,
    CompileSearch,
    NothingToSearchError,
)
from acli_py.application.queries.compile_search.view import CompiledSearch
from acli_py.domain.jql import Catalog, compile_query, looks_like_jql
from acli_py.domain.jql.catalog import spelling

DEFAULT_ORDER = "ORDER BY updated DESC"


def quoted(value: str) -> str:
    """Return a value quoted for JQL."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def one_of(field: str, values: tuple[str, ...]) -> str:
    """Return 'field = "a"', or 'field in ("a", "b")'."""
    if len(values) == 1:
        return f"{field} = {quoted(values[0])}"
    return f"{field} in ({', '.join(quoted(v) for v in values)})"


def split_order(jql: str) -> tuple[str, str]:
    """Return the query's conditions and its 'ORDER BY …' tail ('' when none)."""
    match = re.search(r"(?i)\border\s+by\b.*$", jql)
    if not match:
        return jql.strip(), ""
    return jql[: match.start()].strip(), match.group(0)


def order_by(order: str) -> str:
    """Return 'ORDER BY created DESC' for '-created'; a phrase with spaces as it is."""
    name = order.lstrip("+-").strip()
    if " " in name:
        return f"ORDER BY {name}"
    return f"ORDER BY {name} {'DESC' if order.startswith('-') else 'ASC'}"


@query_handler
def compile_search(request: CompileSearch, search: IssueSearch, catalog: Catalog) -> CompiledSearch:
    """Compile the smart query, and AND it with the filter's JQL and each shortcut."""
    warnings: tuple[str, ...] = ()
    text = request.text.strip()
    if text and not request.raw and not looks_like_jql(text):
        compiled = compile_query(text, resolve=spelling(catalog), default_order="")
        text, warnings = compiled.jql, tuple(compiled.warnings)
    ordering = ""
    clauses: list[str] = []
    for part in (search.filter_jql(request.saved_filter) if request.saved_filter else "", text):
        where, tail = split_order(part)
        ordering = tail or ordering
        if where:
            clauses.append(f"({where})")
    if request.project:
        clauses.append(f"project = {quoted(request.project.upper())}")
    if request.assignee == ME:
        clauses.append("assignee = currentUser()")
    elif request.assignee == NOBODY:
        clauses.append("assignee is EMPTY")
    elif request.assignee:
        clauses.append(f"assignee = {quoted(request.assignee)}")
    for field, values in (
        ("status", request.statuses),
        ("issuetype", request.types),
        ("labels", request.labels),
    ):
        if values:
            clauses.append(one_of(field, values))
    if request.words:
        clauses.append(f"text ~ {quoted(request.words)}")
    if request.open_only:
        clauses.append("statusCategory != Done")
    if not clauses:
        if not request.default_project:
            raise NothingToSearchError("say what to search")
        clauses.append(f"project = {quoted(request.default_project.upper())}")
    ordering = order_by(request.order) if request.order else ordering or DEFAULT_ORDER
    return CompiledSearch(f"{' AND '.join(clauses)} {ordering}", warnings)
