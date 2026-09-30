from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.watch_issue.command import WatchIssue
from acli_py.application.ports import Watchers


@command_handler
def watch_issue(request: WatchIssue, watchers: Watchers) -> Changed:
    """Add or remove the watcher, and say whether they watched it before."""
    key = request.key.strip().upper()
    was = watchers.watching(key, request.account_id)
    if was != request.watch:
        watchers.watch(key, request.account_id, watch=request.watch)
    return Changed(
        key,
        before={"watcher": request.account_id, "watching": was},
        after={"watcher": request.account_id, "watching": request.watch},
    )
