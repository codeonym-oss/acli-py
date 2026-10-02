from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.update_project.command import UpdateProject
from acli_py.application.ports import People, Projects

SHOWN = ("key", "name", "description", "url")


@command_handler
def update_project(request: UpdateProject, projects: Projects, people: People) -> Changed:
    """Change the project, keeping what its key, name, lead, description and URL were."""
    key = request.key.strip().upper()
    spec = request.spec
    old = projects.project(key)
    lead = people.account_id(spec.lead) if spec.lead else None
    projects.update(key, spec, lead)
    given = [k for k in SHOWN if getattr(spec, k) is not None]
    before = {k: getattr(old, k) for k in given}
    after = {k: getattr(spec, k) for k in given}
    if lead:
        before["lead"] = old.lead.account_id if old.lead else None
        after["lead"] = lead
    return Changed(key, before=before, after=after)
