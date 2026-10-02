from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Dashboards
from acli_py.application.queries.get_dashboard.query import GetDashboard
from acli_py.application.queries.get_dashboard.view import DashboardView


@query_handler
def get_dashboard(request: GetDashboard, dashboards: Dashboards) -> DashboardView:
    """Read the dashboard."""
    return DashboardView(dashboards.dashboard(request.dashboard_id.strip()))
