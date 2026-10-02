"""`DashboardsView`: a list of dashboards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import dashboard_json
from acli_py.domain.filters import Dashboard


@dataclass(frozen=True)
class DashboardsView:
    """Dashboards."""

    dashboards: tuple[Dashboard, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return the dashboards as JSON."""
        return [dashboard_json(d) for d in self.dashboards]
