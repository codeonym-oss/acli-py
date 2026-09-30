from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.delete_worklog.command import DeleteWorklog
from acli_py.application.ports import Worklogs


@command_handler
def delete_worklog(request: DeleteWorklog, worklogs: Worklogs) -> Changed:
    """Delete the worklog, keeping how long, when and what in `before`."""
    key = request.key.strip().upper()
    old = worklogs.worklog(key, request.worklog_id)
    worklogs.delete(key, request.worklog_id)
    return Changed(
        key,
        before={
            "worklog": request.worklog_id,
            "spent": old.spent,
            "started": old.started.isoformat() if old.started else "",
            "comment": old.comment,
        },
    )
