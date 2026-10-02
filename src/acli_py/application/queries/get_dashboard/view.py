"""`DashboardView`: one dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import dashboard_json
from acli_py.domain.filters import Dashboard


@dataclass(frozen=True)
class DashboardView:
    """A dashboard."""

    dashboard: Dashboard

    def to_json(self) -> dict[str, Any]:
        """Return the dashboard as JSON."""
        return dashboard_json(self.dashboard)
