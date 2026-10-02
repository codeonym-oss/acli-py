"""Writing issues as they stream in: CSV, JSON, JSON lines or a Markdown table.

Each writer takes one issue at a time, so an export of thousands of issues never holds them
all. `close` finishes the file (JSON's closing bracket); a writer that saw no issue still
writes a valid, empty file.
"""

from __future__ import annotations

import csv
import json
from enum import StrEnum
from typing import TYPE_CHECKING, TextIO

from acli_py.presentation.output import markdown_row, markdown_table

if TYPE_CHECKING:
    from pathlib import Path

    from acli_py.application.queries.issue_columns import IssueColumn
    from acli_py.domain.issue import Issue


class ExportFormat(StrEnum):
    """What an export writes."""

    csv = "csv"
    json = "json"
    jsonl = "jsonl"
    markdown = "markdown"

    @classmethod
    def of(cls, path: Path | None) -> ExportFormat:
        """Return the format a file's extension asks for (.json, .jsonl, .md…); CSV otherwise."""
        suffix = path.suffix.lower().lstrip(".") if path else ""
        return {"json": cls.json, "jsonl": cls.jsonl, "ndjson": cls.jsonl, "md": cls.markdown,
                "markdown": cls.markdown}.get(suffix, cls.csv)  # fmt: skip


class IssueWriter:
    """Writes issues to `out`, one column per `columns`, in `fmt`."""

    def __init__(self, out: TextIO, columns: tuple[IssueColumn, ...], fmt: ExportFormat) -> None:
        self.out = out
        self.columns = columns
        self.fmt = fmt
        self.count = 0
        self._csv = csv.writer(out, lineterminator="\n") if fmt is ExportFormat.csv else None
        self._started = False

    def _start(self) -> None:
        self._started = True
        headers = [c.name for c in self.columns]
        if self._csv is not None:
            self._csv.writerow(headers)
        elif self.fmt is ExportFormat.json:
            self.out.write("[")
        elif self.fmt is ExportFormat.markdown:
            self.out.writelines(f"{line}\n" for line in markdown_table(headers, []))

    def write(self, issue: Issue) -> None:
        """Write one issue."""
        if not self._started:
            self._start()
        if self._csv is not None:
            self._csv.writerow([c.text(issue) for c in self.columns])
        elif self.fmt is ExportFormat.markdown:
            self.out.write(markdown_row(c.text(issue) for c in self.columns) + "\n")
        else:
            data = json.dumps({c.name: c.json(issue) for c in self.columns}, ensure_ascii=False,
                              default=str)  # fmt: skip
            if self.fmt is ExportFormat.json:
                self.out.write(("," if self.count else "") + "\n  " + data)
            else:
                self.out.write(data + "\n")
        self.count += 1

    def close(self) -> None:
        """Finish what was written (and write the header of an empty export)."""
        if not self._started:
            self._start()
        if self.fmt is ExportFormat.json:
            self.out.write("\n]\n" if self.count else "]\n")
        self.out.flush()
