"""`JiraWorkflow`: the `Workflow` port, backed by the Jira REST client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from acli_py.domain import adf
from acli_py.domain.issue import Status
from acli_py.domain.workflow import Transition
from acli_py.infrastructure.jira.client import API

if TYPE_CHECKING:
    from collections.abc import Mapping

    from acli_py.infrastructure.jira.client import JiraClient


class JiraWorkflow:
    """Reads and applies transitions through a `JiraClient`."""

    def __init__(self, client: JiraClient) -> None:
        self.client = client

    def status(self, key: str) -> Status | None:
        """Return the issue's status now."""
        return Status.from_jira(self.client.issue(key, ["status"]).get("fields", {}).get("status"))

    def transitions(self, key: str) -> list[Transition]:
        """Return the transitions available on the issue now."""
        found = (Transition.from_jira(t) for t in self.client.transitions(key))
        return [t for t in found if t is not None]

    def transition(
        self, key: str, transition_id: str, fields: Mapping[str, Any], comment: str
    ) -> None:
        """Apply the transition, with the fields it sets and a Markdown comment."""
        body: dict[str, Any] = {"transition": {"id": transition_id}}
        if fields:
            body["fields"] = dict(fields)
        if comment:
            body["update"] = {"comment": [{"add": {"body": adf.to_adf(comment)}}]}
        self.client.post(f"{API}/issue/{key}/transitions", body)
