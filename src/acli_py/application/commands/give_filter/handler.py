from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.give_filter.command import GiveFilter
from acli_py.application.ports import Filters, People


@command_handler
def give_filter(request: GiveFilter, filters: Filters, people: People) -> Changed:
    """Change the owner, keeping who it was in `before`."""
    filter_id = request.filter_id.strip()
    account = people.account_id(request.to)
    old = filters.filter(filter_id)
    filters.give(filter_id, account)
    return Changed(
        request.item,
        before={"owner": old.owner.account_id if old.owner else None},
        after={"owner": account},
    )
