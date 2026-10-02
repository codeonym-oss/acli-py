from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Workflow
from acli_py.application.queries.list_transitions.query import ListTransitions
from acli_py.application.queries.list_transitions.view import TransitionsView


@query_handler
def list_transitions(request: ListTransitions, workflow: Workflow) -> TransitionsView:
    """Read the transitions."""
    key = request.key.strip().upper()
    return TransitionsView(key, tuple(workflow.transitions(key)))
