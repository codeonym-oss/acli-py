"""Everything the CLI prints: tables, JSON, CSV, messages and dry-run plans.

Results go to stdout; messages, progress, traces and dry-run plans go to stderr, so
`acli-py … --json | jq` and `acli-py … --csv > file.csv` stay clean, and
`acli-py issue search … --output keys | acli-py issue transition - …` pipes one command's
results into the next.
"""

from __future__ import annotations

import csv
import errno
import io
import json
import os
import sys
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from rich import box
from rich.console import Console, Group
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from acli_py.infrastructure.jira.client import PlannedRequest


class _Stdout(Console):
    """Rich's console on stdout, leaving a closed reader (`| head`) to the command's guard."""

    def on_broken_pipe(self) -> None:
        """Stop printing and raise, instead of Rich's own exit (see `common.guarded`)."""
        self.quiet = True
        raise BrokenPipeError(errno.EPIPE, "Broken pipe")


console = _Stdout()
errors = Console(stderr=True)
trace = Console(stderr=True, style="dim")

STATUS_COLORS = {"new": "blue", "indeterminate": "yellow", "done": "green"}
METHOD_COLORS = {"POST": "green", "PUT": "yellow", "DELETE": "red", "PATCH": "yellow"}


class Format(StrEnum):
    """How a command prints its results."""

    table = "table"
    json = "json"
    csv = "csv"
    keys = "keys"  # one key (or id) per line, for piping into another command
    jsonl = "jsonl"  # one JSON object per line, likewise


def pick_format(as_json: bool, as_csv: bool = False, chosen: Format | None = None) -> Format:
    """Return the output format chosen by --json, --csv or --output."""
    picked = [f for f, on in ((Format.json, as_json), (Format.csv, as_csv)) if on]
    if chosen is not None:
        picked.append(chosen)
    if len(set(picked)) > 1:
        raise ValueError("choose one of --json, --csv and --output")
    return picked[0] if picked else Format.table


def key_of(row: Any) -> str:
    """Return what names a row for the next command: its key, id, account id or name."""
    if not isinstance(row, dict):
        return str(row)
    for name in ("key", "id", "accountId", "name"):
        if row.get(name) not in (None, ""):
            return str(row[name])
    return ""


@dataclass(frozen=True)
class Column:
    """A table/CSV column: a header and how to read the cell from a row."""

    header: str
    get: Callable[[Any], Any]
    style: str | None = None
    justify: str = "left"
    no_wrap: bool = False

    def text(self, row: Any) -> str:
        """Return the cell as plain text."""
        value = self.get(row)
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return ", ".join(str(v) for v in value)
        return str(value)


def dig(data: Any, *path: str | int, default: Any = None) -> Any:
    """Follow keys/indexes into nested JSON, returning `default` when any step is missing."""
    for step in path:
        if isinstance(data, dict):
            data = data.get(step)  # type: ignore[arg-type]
        elif isinstance(data, list) and isinstance(step, int) and -len(data) <= step < len(data):
            data = data[step]
        else:
            return default
        if data is None:
            return default
    return data


def col(header: str, *path: str | int, **kwargs: Any) -> Column:
    """Return a column reading a nested JSON path."""
    return Column(header, lambda row: dig(row, *path), **kwargs)


def print_json(data: Any) -> None:
    """Print JSON to stdout, uncoloured, so it pipes cleanly."""
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def lines(texts: Iterable[str]) -> None:
    """Print lines of plain text to stdout, for the next command to read."""
    sys.stdout.write("".join(f"{line}\n" for line in texts))
    sys.stdout.flush()


def silence_stdout() -> None:
    """Send what is left for stdout nowhere: its reader has gone (`acli-py … | head`).

    Else Python's last flush at exit fails again, and says so on stderr.
    """
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError, io.UnsupportedOperation):
        pass  # not a real file (tests capture it): nothing will flush it at exit


def emit(
    rows: Iterable[Any],
    columns: list[Column],
    fmt: Format,
    *,
    title: str | None = None,
    empty: str = "Nothing found.",
) -> list[Any]:
    """Print rows as a table, JSON (the raw objects), CSV, keys or JSON lines; return the rows."""
    rows = list(rows)
    if fmt is Format.json:
        print_json(rows)
        return rows
    if fmt in (Format.keys, Format.jsonl):
        lines = (
            key_of(row) if fmt is Format.keys else json.dumps(row, ensure_ascii=False, default=str)
            for row in rows
        )
        sys.stdout.write("".join(f"{line}\n" for line in lines))
        sys.stdout.flush()
        return rows
    if fmt is Format.csv:
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow([c.header for c in columns])
        writer.writerows([c.text(row) for c in columns] for row in rows)
        sys.stdout.write(buffer.getvalue())
        sys.stdout.flush()
        return rows
    if not rows:
        info(empty)
        return rows
    table = Table(box=box.SIMPLE_HEAD, header_style="bold", pad_edge=False, title=title)
    for c in columns:
        table.add_column(c.header, style=c.style, justify=c.justify, no_wrap=c.no_wrap)  # type: ignore[arg-type]
    for row in rows:
        table.add_row(*(escape(c.text(row)) for c in columns))
    console.print(table)
    return rows


def details(title: str, rows: Iterable[tuple[str, Any]], subtitle: str | None = None) -> Panel:
    """Return a titled panel of label/value rows, skipping empty values."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", justify="right", no_wrap=True)
    grid.add_column(overflow="fold")
    for label, value in rows:
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(v) for v in value)
        elif isinstance(value, (int, float)):
            value = str(value)
        grid.add_row(label, value)
    return Panel(
        grid,
        title=f"[bold]{title}[/]",
        subtitle=subtitle,
        title_align="left",
        subtitle_align="right",
        box=box.ROUNDED,
        border_style="blue",
        expand=False,
    )


def status_text(status: dict | None) -> str:
    """Return a status name coloured by its category, as Rich markup."""
    if not status:
        return ""
    colour = STATUS_COLORS.get(dig(status, "statusCategory", "key", default=""), "white")
    return f"[{colour}]{escape(status.get('name', '?'))}[/]"


# ── messages ─────────────────────────────────────────────────────────────────


def success(message: str) -> None:
    """Print a green tick and a message (stderr)."""
    errors.print(f"[bold green]✔[/] {message}")


def info(message: str) -> None:
    """Print a neutral message (stderr)."""
    errors.print(f"[dim]•[/] {message}")


def warn(message: str) -> None:
    """Print a yellow warning (stderr)."""
    errors.print(f"[bold yellow]![/] {message}")


def error(message: str) -> None:
    """Print a red cross and a message (stderr)."""
    errors.print(f"[bold red]✘[/] {message}")


def readable(body: Any) -> Any:
    """Return a request body with rich text (ADF) shown as Markdown, for dry-run plans."""
    from acli_py.domain import adf

    if adf.is_adf(body):
        return f"ADF: {adf.to_text(body)}"
    if isinstance(body, dict):
        return {k: readable(v) for k, v in body.items()}
    if isinstance(body, list):
        return [readable(v) for v in body]
    return body


def show_plan(planned: PlannedRequest) -> None:
    """Print a write that a dry run did not send."""
    colour = METHOD_COLORS.get(planned.method, "white")
    query = "&".join(f"{k}={v}" for k, v in planned.params.items())
    target = planned.path + (f"?{query}" if query else "")
    title = f"[bold magenta]DRY RUN[/] [bold {colour}]{planned.method}[/] {escape(target)}"
    if planned.body is None and not planned.files:
        errors.print(title)
        return
    parts: list[Any] = []
    if planned.files:
        parts.append(f"[dim]upload:[/] {escape(', '.join(planned.files))}")
    if planned.body is not None:
        text = json.dumps(readable(planned.body), indent=2, ensure_ascii=False, default=str)
        if text.count("\n") > 60:
            text = "\n".join([*text.split("\n")[:60], "  …"])
        parts.append(Syntax(text, "json", theme="ansi_dark", background_color="default"))
    errors.print(
        Panel(Group(*parts), title=title, title_align="left", border_style="magenta", expand=False)
    )
