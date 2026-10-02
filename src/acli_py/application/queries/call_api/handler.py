from __future__ import annotations

from typing import Any

from mediary.cqrs import query_handler

from acli_py.application.ports import RawApi
from acli_py.application.queries.call_api.query import ApiGet


def params_of(params: tuple[tuple[str, tuple[str, ...]], ...]) -> dict[str, Any]:
    """Return query parameters as requests takes them: one value, or a list of several."""
    return {name: values[0] if len(values) == 1 else list(values) for name, values in params}


@query_handler
def api_get(request: ApiGet, api: RawApi) -> Any:
    """Read the endpoint."""
    return api.request("GET", request.path, params_of(request.params))
