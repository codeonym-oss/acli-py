from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_links.view import LinksView


@query
@dataclass(frozen=True)
class ListLinks(Query[LinksView]):
    """Issue `key`'s links, read from its side ('blocks DEMO-2', 'is blocked by DEMO-3')."""

    key: str
