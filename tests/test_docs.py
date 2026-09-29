"""The command reference in docs/commands must match the CLI."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_generator():
    spec = importlib.util.spec_from_file_location("cli_docs", ROOT / "scripts" / "cli_docs.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_command_reference_is_up_to_date(capsys):
    assert load_generator().main(["--check"]) == 0, (
        "docs/commands is stale; run `uv run python scripts/cli_docs.py`:\n"
        + capsys.readouterr().out
    )


def test_every_group_is_in_the_reference():
    index = (ROOT / "docs" / "commands" / "index.md").read_text(encoding="utf-8")
    for group in (
        "auth",
        "config",
        "issue",
        "project",
        "board",
        "sprint",
        "filter",
        "field",
        "api",
    ):
        assert f"\n{group}\n" in index
