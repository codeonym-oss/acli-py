from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.archive_project.command import ArchiveProject
from acli_py.application.ports import Projects


@command_handler
def archive_project(request: ArchiveProject, projects: Projects) -> Changed:
    """Archive the project."""
    key = request.key.strip().upper()
    projects.archive(key)
    return Changed(key, before={"project": "live"}, after={"project": "archived"})
