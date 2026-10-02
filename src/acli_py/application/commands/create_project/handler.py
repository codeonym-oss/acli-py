from __future__ import annotations

from dataclasses import replace

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.create_project.command import CreateProject
from acli_py.application.ports import People, Projects


@command_handler
def create_project(request: CreateProject, projects: Projects, people: People) -> Changed:
    """Create the project; `after` names it, and the schemes it shares."""
    spec = request.spec
    shared: dict[str, int] = {}
    if request.like:
        shared = projects.shared_configuration(request.like.strip().upper())
        spec = replace(spec, template=None)
    lead = people.account_id(spec.lead or "@me")
    project_id = projects.create(spec, lead, shared)
    schemes = tuple(k.removesuffix("Scheme") for k in shared if k.endswith("Scheme"))
    return Changed(
        request.key,
        after={"project": request.key, "id": project_id, "name": spec.name, "shares": schemes},
    )
