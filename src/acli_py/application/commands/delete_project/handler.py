from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.delete_project.command import DeleteProject
from acli_py.application.ports import Projects


@command_handler
def delete_project(request: DeleteProject, projects: Projects) -> Changed:
    """Delete the project."""
    key = request.key.strip().upper()
    projects.delete(key, permanent=request.permanent)
    return Changed(key, after={"project": "deleted" if request.permanent else "trashed"})
