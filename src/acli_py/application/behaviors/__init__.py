"""Behaviors: what wraps every message on the bus, whatever its handler.

Each is a mediary behavior, an object with `async handle(message, next)`; the bus decides the
order and which kinds of message (queries, commands) each one wraps.
"""

from acli_py.application.behaviors.activity import Activity, Entry, describe
from acli_py.application.behaviors.announce import Announce
from acli_py.application.behaviors.cache import CACHE_SECONDS, QueryCache

__all__ = ["CACHE_SECONDS", "Activity", "Announce", "Entry", "QueryCache", "describe"]
