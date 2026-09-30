from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_attachments.view import AttachmentsView


@query
@dataclass(frozen=True)
class ListAttachments(Query[AttachmentsView]):
    """The files attached to issue `key`."""

    key: str
