from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.create_filter.command import CreateFilter
from acli_py.application.ports import Filters


@command_handler
def create_filter(request: CreateFilter, filters: Filters) -> Changed:
    """Save the filter; `after` names it."""
    filter_id = filters.create(
        request.name, request.jql, request.description, request.favourite, request.shares
    )
    return Changed(
        f"filter {filter_id}", after={"filter": filter_id, "name": request.name, "jql": request.jql}
    )
