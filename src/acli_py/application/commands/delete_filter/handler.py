from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.delete_filter.command import DeleteFilter
from acli_py.application.ports import Filters


@command_handler
def delete_filter(request: DeleteFilter, filters: Filters) -> Changed:
    """Delete the filter, keeping its name and query in `before`."""
    filter_id = request.filter_id.strip()
    old = filters.filter(filter_id)
    filters.delete(filter_id)
    return Changed(request.item, before={"filter": filter_id, "name": old.name, "jql": old.jql})
