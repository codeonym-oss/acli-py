from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.set_filter_columns.command import SetFilterColumns
from acli_py.application.ports import Filters


@command_handler
def set_filter_columns(request: SetFilterColumns, filters: Filters) -> Changed:
    """Set the columns, keeping the old ones in `before`."""
    filter_id = request.filter_id.strip()
    old = tuple(c.field for c in filters.columns(filter_id))
    filters.set_columns(filter_id, request.columns)
    return Changed(request.item, before={"columns": old}, after={"columns": request.columns})
