from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.trash_field.command import TrashField
from acli_py.application.ports import SiteFields


@command_handler
def trash_field(request: TrashField, fields: SiteFields) -> Changed:
    """Trash the field."""
    fields.trash(request.field_id.strip())
    return Changed(request.item, after={"field": "trashed"})
