from __future__ import annotations

from dataclasses import dataclass

from mediary.cqrs import Query, query

from acli_py.application.queries.get_dashboard.view import DashboardView


@query
@dataclass(frozen=True)
class GetDashboard(Query[DashboardView]):
    """Dashboard `dashboard_id`."""

    dashboard_id: str
