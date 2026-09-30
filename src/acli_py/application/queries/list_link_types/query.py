from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_link_types.view import LinkTypesView


@query
@dataclass(frozen=True)
class ListLinkTypes(Query[LinkTypesView]):
    """The site's link types: 'Blocks (blocks / is blocked by)'."""
