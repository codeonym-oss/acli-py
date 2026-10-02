from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.create_field.command import CreateField
from acli_py.application.ports import SiteFields
from acli_py.domain.fields import custom_field_type


@command_handler
def create_field(request: CreateField, fields: SiteFields) -> Changed:
    """Create the field; `after` names it."""
    type_key, searcher = custom_field_type(request.type, request.searcher)
    field_id = fields.create(request.name, type_key, searcher, request.description)
    return Changed(
        f"field {field_id}", after={"field": field_id, "name": request.name, "type": type_key}
    )
