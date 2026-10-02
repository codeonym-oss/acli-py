"""The command reference in docs/commands must match the CLI."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

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
        "log",
        "undo",
        "standup",
        "git",
        "alias",
    ):
        assert f"\n{group}\n" in index


def _snippets(path: Path) -> list[str]:
    """Return every `acli-py …` code span in a page, alternatives included (`… / --x`)."""
    import re

    return re.findall(r"`(acli-py [^`]+)`", path.read_text(encoding="utf-8"))


def test_documented_commands_and_options_exist():
    """Every `acli-py …` in the guides and README names real commands and options."""
    import shlex

    import typer

    from acli_py.presentation.cli import app

    root: Any = typer.main.get_command(app)  # Typer bundles its own click: typed loosely

    def option(command: Any, name: str) -> Any:
        for param in command.params:
            if name in (*param.opts, *getattr(param, "secondary_opts", [])):
                return param
        return None

    def check(words: list[str]) -> str | None:
        command: Any = root
        index = 0
        while index < len(words):
            word = words[index]
            if word == "…" or (command is root and word.startswith("@")):
                return None  # "and so on", or an alias: whatever it runs
            if word.startswith("-") and not word[1:2].isdigit():
                param = option(command, word.split("=", 1)[0]) or option(root, word)
                if param is None:
                    return f"no option {word}"
                takes_value = not (param.is_flag or getattr(param, "count", False))
                index += 2 if takes_value and "=" not in word else 1
                continue
            if hasattr(command, "commands"):
                names = word.split("/")  # "search/view": both must exist
                missing = [n for n in names if n not in command.commands]
                if missing:
                    return f"no command {missing[0]!r}"
                command = command.commands[names[0]]
            index += 1
        return None

    pages = [ROOT / "README.md", *sorted((ROOT / "docs" / "guide").glob("*.md"))]
    problems = []
    for page in pages:
        for snippet in _snippets(page):
            try:
                words = shlex.split(snippet.split(" #")[0])[1:]
            except ValueError:
                continue
            if problem := check(words):
                problems.append(f"{page.name}: {snippet!r}: {problem}")
    assert not problems, "\n".join(problems)
