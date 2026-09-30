"""The terminal to ask questions on, even in the middle of a pipe.

`acli-py issue search … --output keys | acli-py issue transition - --to Done` reads its
issues from stdin, so its question can't be answered there: it is asked on the controlling
terminal instead (`/dev/tty`, or the console on Windows). With no terminal at all (cron, CI)
there is nobody to ask, and commands refuse to change anything without `--yes`.
"""

from __future__ import annotations

import os
import sys
from typing import TextIO

import typer

# Where to read the answer from and write the question to, when stdin is taken.
TTY = ("CONIN$", "CONOUT$") if os.name == "nt" else ("/dev/tty", "/dev/tty")
YES = ("y", "yes")


def open_tty() -> tuple[TextIO, TextIO] | None:
    """Open the controlling terminal to read and write, or return None when there is none."""
    reading, writing = TTY
    try:
        reader = open(reading, encoding="utf-8")  # noqa: SIM115 - closed by the caller
    except OSError:
        return None
    try:
        writer = open(writing, "w", encoding="utf-8")  # noqa: SIM115
    except OSError:
        reader.close()
        return None
    return reader, writer


def available() -> bool:
    """Return whether there is a terminal to ask questions on."""
    if sys.stdin.isatty():
        return True
    tty = open_tty()
    if tty is None:
        return False
    for stream in tty:
        stream.close()
    return True


def ask(question: str) -> bool:
    """Ask a yes/no question, no by default: on stdin, else on the terminal; no terminal is no."""
    if sys.stdin.isatty():
        return typer.confirm(question, default=False, err=True)
    tty = open_tty()
    if tty is None:
        return False
    reader, writer = tty
    with reader, writer:
        writer.write(f"{question} [y/N]: ")
        writer.flush()
        return reader.readline().strip().lower() in YES
