from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Projects
from acli_py.application.queries.list_versions.query import ListVersions
from acli_py.application.queries.list_versions.view import VersionsView


@query_handler
def list_versions(request: ListVersions, projects: Projects) -> VersionsView:
    """Read the versions."""
    key = request.key.strip().upper()
    found = projects.versions(key)
    if request.unreleased:
        found = [v for v in found if not v.released]
    return VersionsView(key, tuple(found))
