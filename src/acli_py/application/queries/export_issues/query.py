from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import StreamQuery, stream_query

from acli_py.domain.issue import Issue


@stream_query
@dataclass(frozen=True)
class ExportIssues(StreamQuery[Issue]):
    """Every issue `jql` finds, in its order, with the fields the columns `fields` need.

    `limit` stops after that many (None: all).
    """

    jql: str
    fields: tuple[str, ...] = ()
    limit: int | None = None
