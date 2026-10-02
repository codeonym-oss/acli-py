from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.restore_project.command import RestoreProject
from acli_py.application.ports import Projects


@command_handler
def restore_project(request: RestoreProject, projects: Projects) -> Changed:
    """Restore the project."""
    key = request.key.strip().upper()
    projects.restore(key)
    return Changed(key, after={"project": "live"})
