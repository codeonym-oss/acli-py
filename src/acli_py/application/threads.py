"""Reading many issues at once: blocking calls spread over a few worker threads."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

T = TypeVar("T")
R = TypeVar("R")

# Reads in flight at once: enough to hide the round trips, few enough not to be rate limited.
READS = 8


async def map_in_threads(fn: Callable[[T], R], items: Iterable[T], limit: int = READS) -> list[R]:
    """Return `fn` of each item, in order, running up to `limit` calls at a time."""
    gate = asyncio.Semaphore(limit)

    async def one(item: T) -> R:
        async with gate:
            return await asyncio.to_thread(fn, item)

    return list(await asyncio.gather(*(one(i) for i in items)))
