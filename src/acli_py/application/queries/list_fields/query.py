from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_fields.view import FieldsView


@query
@dataclass(frozen=True)
class ListFields(Query[FieldsView]):
    """Fields whose name or id contain `query`; only `custom` ones, or those `trashed`."""

    query: str | None = None
    custom: bool = False
    trashed: bool = False
