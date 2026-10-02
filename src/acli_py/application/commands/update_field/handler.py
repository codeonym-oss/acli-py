from __future__ import annotations

from mediary.cqrs import command_handler

from acli_py.application.changes import Changed
from acli_py.application.commands.update_field.command import FIELDS, UpdateField
from acli_py.application.ports import SiteFields


@command_handler
def update_field(request: UpdateField, fields: SiteFields) -> Changed:
    """Change the field; `after` says how."""
    fields.update(
        request.field_id.strip(),
        name=request.name,
        description=request.description,
        searcher=request.searcher,
    )
    return Changed(
        request.item, after={f: v for f in FIELDS if (v := getattr(request, f)) is not None}
    )
