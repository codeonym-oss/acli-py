"""`AuditFile`: the `AuditLog` port, as JSON lines in a file next to the config."""

from __future__ import annotations

import json
import os
import stat
from typing import TYPE_CHECKING

from acli_py.infrastructure.config import config_dir, ensure_private_dir

if TYPE_CHECKING:
    from pathlib import Path

    from acli_py.application.changes import AuditRecord

FILE_NAME = "audit.jsonl"


def default_path() -> Path:
    """Return where the audit log lives: `audit.jsonl` in the config directory."""
    return config_dir() / FILE_NAME


class AuditFile:
    """Appends one JSON object per run: time (UTC, ISO), command, keys, and each change.

    `changes` holds each issue's fields before and after; `failed` maps the issues the run
    failed on to why.

    The file is readable by its owner only (on POSIX). A log that cannot be written never
    undoes or fails the change it records: the change has happened by then.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path()

    def record(self, entry: AuditRecord) -> None:
        """Append `entry` as one line."""
        line = json.dumps(
            {
                "at": entry.at.isoformat(),
                "command": entry.command,
                "keys": list(entry.keys),
                "changes": [
                    {"key": c.key, "before": dict(c.before), "after": dict(c.after)}
                    for c in entry.changes
                ],
                "failed": dict(entry.failed),
            },
            ensure_ascii=False,
            default=str,
        )
        try:
            ensure_private_dir(self.path.parent)
            flags, mode = os.O_WRONLY | os.O_APPEND | os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR
            fd = os.open(self.path, flags, mode)
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            return
