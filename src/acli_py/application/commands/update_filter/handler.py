from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.update_filter.command import UpdateFilter
from acli_py.application.ports import Filters

TRACKED = ("name", "jql", "description")


@command_handler
def update_filter(request: UpdateFilter, filters: Filters) -> Changed:
    """Change the filter, keeping what its name, query and description were."""
    filter_id = request.filter_id.strip()
    old = filters.filter(filter_id)
    filters.update(
        filter_id,
        name=request.name or old.name,
        jql=request.jql,
        description=request.description,
        shares=request.shares,
        edit_shares=request.edit_shares,
    )
    given = [f for f in TRACKED if getattr(request, f) is not None]
    return Changed(
        request.item,
        before={f: getattr(old, f) for f in given},
        after={f: getattr(request, f) for f in given},
    )
