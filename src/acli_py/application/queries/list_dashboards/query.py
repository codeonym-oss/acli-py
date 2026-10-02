from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.list_dashboards.view import DashboardsView


@query
@dataclass(frozen=True)
class ListDashboards(Query[DashboardsView]):
    """Up to `limit` dashboards (None: all) by `name` and `owner` ('@me', an email)."""

    name: str | None = None
    owner: str | None = None
    limit: int | None = 50
