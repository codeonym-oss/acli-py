from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_versions.view import VersionsView


@query
@dataclass(frozen=True)
class ListVersions(Query[VersionsView]):
    """The versions of project `key`; only the unreleased ones with `unreleased`."""

    key: str
    unreleased: bool = False
