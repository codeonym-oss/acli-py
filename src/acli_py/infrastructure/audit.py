"""The `AuditLog` port: `AuditFile`, JSON lines next to the config, and `AuditMemory`."""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime
from typing import TYPE_CHECKING, Any

from acli_py.application.changes import AuditRecord, Changed
from acli_py.infrastructure.config import config_dir, ensure_private_dir

if TYPE_CHECKING:
    from pathlib import Path

FILE_NAME = "audit.jsonl"


def default_path() -> Path:
    """Return where the audit log lives: `audit.jsonl` in the config directory."""
    return config_dir() / FILE_NAME


class AuditFile:
    """Appends one JSON object per run: time (UTC, ISO), command, keys, and each change.

    `changes` holds each issue's fields before and after; `failed` maps the issues the run
    failed on to why; `undoes` (on an undo only) is the id of the record it reversed. A
    record's id is its line number, so the log stays a plain append-only file.

    The file is readable by its owner only (on POSIX). A log that cannot be written never
    undoes or fails the change it records: the change has happened by then.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path()

    def record(self, entry: AuditRecord) -> None:
        """Append `entry` as one line."""
        data: dict[str, Any] = {
            "at": entry.at.isoformat(),
            "command": entry.command,
            "keys": list(entry.keys),
            "changes": [
                {"key": c.key, "before": dict(c.before), "after": dict(c.after)}
                for c in entry.changes
            ],
            "failed": dict(entry.failed),
        }
        if entry.undoes:
            data["undoes"] = entry.undoes
        line = json.dumps(data, ensure_ascii=False, default=str)
        try:
            ensure_private_dir(self.path.parent)
            flags, mode = os.O_WRONLY | os.O_APPEND | os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR
            fd = os.open(self.path, flags, mode)
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            return

    def entries(self) -> list[AuditRecord]:
        """Read the log back, oldest first; a line that isn't a record is skipped."""
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        found = []
        for number, line in enumerate(lines, 1):
            try:
                found.append(_parse(json.loads(line), str(number)))
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        return found


def _parse(data: dict[str, Any], entry_id: str) -> AuditRecord:
    changes = tuple(
        Changed(c["key"], c.get("before") or {}, c.get("after") or {}) for c in data["changes"]
    )
    at = datetime.fromisoformat(data["at"])
    return AuditRecord(
        data["command"], changes, at, data.get("failed") or {}, data.get("undoes"), entry_id
    )


class AuditMemory:
    """Keeps the records in memory (for tests, and front ends that keep no file)."""

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def record(self, entry: AuditRecord) -> None:
        """Keep `entry`."""
        self.records.append(entry)

    def entries(self) -> list[AuditRecord]:
        """Return the records, each with its place as its id."""
        return [
            AuditRecord(r.command, r.changes, r.at, r.failed, r.undoes, str(n))
            for n, r in enumerate(self.records, 1)
        ]
