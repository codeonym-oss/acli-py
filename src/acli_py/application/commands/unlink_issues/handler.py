from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.unlink_issues.command import UnlinkIssues
from acli_py.application.ports import IssueLinks


@command_handler
def unlink_issues(request: UnlinkIssues, links: IssueLinks) -> Changed:
    """Remove the link; `before` says which issues it joined, so it can be made again."""
    link = links.get_link(request.link_id)
    links.unlink(request.link_id)
    return Changed(
        link.outward,
        before={
            "link": str(link),
            "type": link.type.name,
            "outward": link.outward,
            "inward": link.inward,
        },
    )
