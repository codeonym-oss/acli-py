from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.link_issues.command import LinkIssues
from acli_py.application.ports import IssueLinks
from acli_py.domain import adf
from acli_py.domain.links import LinkDirection


@command_handler
def link_issues(request: LinkIssues, links: IssueLinks) -> Changed:
    """Store the link; `Changed` is on its outward issue and says which link it was."""
    link = LinkDirection(links.link_types()).link(request.source, request.kind, request.target)
    links.link(link, adf.to_adf(request.comment) if request.comment else None)
    return Changed(
        link.outward,
        after={
            "link": str(link),
            "type": link.type.name,
            "outward": link.outward,
            "inward": link.inward,
        },
    )
