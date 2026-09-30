from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.log_work.command import LogWork
from acli_py.application.ports import Worklogs
from acli_py.domain import adf


@command_handler
def log_work(request: LogWork, worklogs: Worklogs) -> Changed:
    """Log the work; `after` names the new worklog."""
    key = request.key.strip().upper()
    spent = request.spent.strip()
    comment = adf.to_adf(request.comment) if request.comment else None
    worklog = worklogs.log(key, spent, comment, request.started, request.remaining)
    return Changed(key, after={"worklog": worklog, "spent": spent})
