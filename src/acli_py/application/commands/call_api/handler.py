from __future__ import annotations

from typing import Any

from mediary.cqrs import command_handler

from acli_py.application.commands.call_api.command import CallApi
from acli_py.application.ports import RawApi
from acli_py.application.queries.call_api.handler import params_of


@command_handler
def call_api(request: CallApi, api: RawApi) -> Any:
    """Send the request."""
    return api.request(
        request.method.upper(), request.path, params_of(request.params), request.body
    )
