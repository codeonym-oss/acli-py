from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import SiteFields
from acli_py.application.queries.list_fields.query import ListFields
from acli_py.application.queries.list_fields.view import FieldsView


@query_handler
def list_fields(request: ListFields, fields: SiteFields) -> FieldsView:
    """Read the fields: Jira's own first, then custom ones, each by name."""
    if request.trashed:
        found = fields.trashed(request.query)
    else:
        found = [
            f
            for f in fields.fields()
            if (f.custom or not request.custom) and (not request.query or f.matches(request.query))
        ]
    return FieldsView(tuple(sorted(found, key=lambda f: (f.custom, f.name.lower()))))
