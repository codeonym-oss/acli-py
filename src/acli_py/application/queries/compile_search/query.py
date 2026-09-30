from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.compile_search.view import CompiledSearch

ME = "@me"
NOBODY = "none"


class NothingToSearchError(ValueError):
    """The search names nothing to look for, and there is no default project."""


@query
@dataclass(frozen=True)
class CompileSearch(Query[CompiledSearch]):
    """What to search for, as one JQL query.

    `text` is a smart query ('@me is:open #web') or JQL; `raw` sends it as JQL whatever it
    looks like. The rest narrow it down: `assignee` is `ME`, `NOBODY` or an account id, and
    `order` a field, '-' first for descending. With nothing else, `default_project` is searched.
    """

    text: str = ""
    raw: bool = False
    saved_filter: str = ""
    project: str = ""
    assignee: str = ""
    statuses: tuple[str, ...] = ()
    types: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    words: str = ""
    open_only: bool = False
    order: str = ""
    default_project: str = ""
