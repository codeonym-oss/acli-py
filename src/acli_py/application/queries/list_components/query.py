from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_components.view import ComponentsView


@query
@dataclass(frozen=True)
class ListComponents(Query[ComponentsView]):
    """The components of project `key`."""

    key: str
