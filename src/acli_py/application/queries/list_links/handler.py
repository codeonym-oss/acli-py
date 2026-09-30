from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import IssueLinks
from acli_py.application.queries.list_links.query import ListLinks
from acli_py.application.queries.list_links.view import LinksView


@query_handler
def list_links(request: ListLinks, links: IssueLinks) -> LinksView:
    """Read the links."""
    key = request.key.strip().upper()
    return LinksView(key, links.links_of(key))
