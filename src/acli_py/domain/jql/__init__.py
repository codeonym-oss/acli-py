"""Queries: JQL completion, and the smart query syntax that compiles to JQL."""

from acli_py.domain.jql.catalog import Catalog, FieldRef, FunctionRef, StaticCatalog, Value
from acli_py.domain.jql.complete import Completer, Completion, Suggestion
from acli_py.domain.jql.smart import Compiled, compile_query, looks_like_jql

__all__ = [
    "Catalog",
    "Compiled",
    "Completer",
    "Completion",
    "FieldRef",
    "FunctionRef",
    "StaticCatalog",
    "Suggestion",
    "Value",
    "compile_query",
    "looks_like_jql",
]
