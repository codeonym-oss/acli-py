from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.star_filter.command import StarFilter
from acli_py.application.ports import Filters


@command_handler
def star_filter(request: StarFilter, filters: Filters) -> Changed:
    """Star or unstar the filter."""
    filters.star(request.filter_id.strip(), star=request.star)
    return Changed(
        request.item, before={"favourite": not request.star}, after={"favourite": request.star}
    )
