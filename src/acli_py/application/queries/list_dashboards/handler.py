from __future__ import annotations

from mediary.cqrs import query_handler

from acli_py.application.ports import Dashboards, People
from acli_py.application.queries.list_dashboards.query import ListDashboards
from acli_py.application.queries.list_dashboards.view import DashboardsView


@query_handler
def list_dashboards(
    request: ListDashboards, dashboards: Dashboards, people: People
) -> DashboardsView:
    """Find the dashboards."""
    owner = people.account_id(request.owner) if request.owner else None
    found = dashboards.search(name=request.name, owner=owner, limit=request.limit)
    return DashboardsView(tuple(found))
