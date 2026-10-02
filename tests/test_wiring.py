"""The composition root wires every use case: checked through mediary's `registrations()`."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import TYPE_CHECKING

import pytest
from mediary.cqrs import Command, Event, Query, StreamQuery

from acli_py.application import commands, events, queries
from acli_py.application.behaviors import Activity, Announce, Confirm, QueryCache
from acli_py.application.events.issue_changed.event import IssueChanged
from acli_py.bootstrap import build_bus
from acli_py.infrastructure.jira.client import JiraClient
from acli_py.infrastructure.jira.site import Site
from tests import fake_jira

if TYPE_CHECKING:
    from types import ModuleType

    from mediary import Registrations

MESSAGE_BASES = (Command, Query, StreamQuery, Event)


@pytest.fixture
def registered(fake) -> Registrations:
    _, url = fake
    client = JiraClient(url, fake_jira.EMAIL, fake_jira.TOKEN, retries=0)
    return build_bus(Site(client, url)).mediator.registrations()


def messages_in(package: ModuleType) -> set[type]:
    """Return the commands, queries and events defined under `package`."""
    found: set[type] = set()
    for info in pkgutil.walk_packages(package.__path__, f"{package.__name__}."):
        module = importlib.import_module(info.name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ == module.__name__ and issubclass(cls, MESSAGE_BASES):
                found.add(cls)
    return found


def test_every_command_and_query_has_one_handler(registered):
    handled = [r.message_type for r in registered.handlers]
    messages = messages_in(commands) | messages_in(queries)
    assert len(messages) > 30  # the scan found the use cases, not nothing
    for message in messages:
        assert handled.count(message) == 1, f"{message.__name__} has no single handler"


def test_every_event_has_a_subscriber(registered):
    handled = {r.message_type for r in registered.handlers}
    assert messages_in(events) == {IssueChanged}
    assert IssueChanged in handled


def test_behaviors_wrap_in_order(registered):
    wrapping = [(type(r.behavior), r.kinds) for r in registered.behaviors]
    assert wrapping == [
        (Activity, None),
        (Confirm, frozenset({"command"})),
        (Announce, frozenset({"command"})),
        (QueryCache, frozenset({"query"})),
    ]
