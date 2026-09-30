from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import IssueLinks
from acli_py.application.queries.list_link_types.query import ListLinkTypes
from acli_py.application.queries.list_link_types.view import LinkTypesView


@query_handler
def list_link_types(request: ListLinkTypes, links: IssueLinks) -> LinkTypesView:
    """Read the link types."""
    return LinkTypesView(links.link_types())
