from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.archive_issue.command import ArchiveIssue
from acli_py.application.ports import IssueStore


@command_handler
def archive_issue(request: ArchiveIssue, store: IssueStore) -> Changed:
    """Archive or restore the issue."""
    key = request.key.strip().upper()
    store.archive(key, archive=request.archive)
    return Changed(
        key, before={"archived": not request.archive}, after={"archived": request.archive}
    )
