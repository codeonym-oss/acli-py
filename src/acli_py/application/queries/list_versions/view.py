"""`VersionsView`: a project's versions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acli_py.application.queries.shapes import version_json
from acli_py.domain.projects import Version


@dataclass(frozen=True)
class VersionsView:
    """The versions of project `key`."""

    key: str
    versions: tuple[Version, ...]

    def to_json(self) -> list[dict[str, Any]]:
        """Return the versions as JSON."""
        return [version_json(v) for v in self.versions]
