from __future__ import annotations

from typing import Any

from mediary.cqrs import query_handler

from acli_py.application.ports import IssueFields
from acli_py.application.queries.build_fields.query import BuildFields, ResolveFieldValues


@query_handler
def build_fields(request: BuildFields, fields: IssueFields) -> dict[str, Any]:
    """Resolve what was typed."""
    return fields.fields_for(request.wanted, creating=request.creating)


@query_handler
def resolve_field_values(request: ResolveFieldValues, fields: IssueFields) -> dict[str, Any]:
    """Resolve the assignments."""
    return fields.field_values(request.assignments)
