from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.restore_field.command import RestoreField
from acli_py.application.ports import SiteFields


@command_handler
def restore_field(request: RestoreField, fields: SiteFields) -> Changed:
    """Restore the field."""
    fields.restore(request.field_id.strip())
    return Changed(request.item, after={"field": "live"})
