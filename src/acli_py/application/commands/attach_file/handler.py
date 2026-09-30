from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.attach_file.command import AttachFile
from acli_py.application.ports import Attachments


@command_handler
def attach_file(request: AttachFile, attachments: Attachments) -> Changed:
    """Upload the file; `after` names the attachments it made."""
    key = request.key.strip().upper()
    uploaded = attachments.upload(key, request.path)
    return Changed(key, after={"file": request.path.name, "attachments": [a.id for a in uploaded]})
