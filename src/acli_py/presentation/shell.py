"""`acli-py shell`: every `acli-py` command at a prompt, with completion that knows your site.

Completion walks the real command tree, so it never drifts from the CLI: commands, options and
their help, choices, and live values — issue keys, projects, statuses, people, labels — from the
site. Inside a JQL or smart query (`issue search`, `--jql`) it completes the query itself.
Commands run in-process, so each one starts instantly.
"""

from __future__ import annotations

import re
import shlex
from typing import TYPE_CHECKING, Any

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import CompleteEvent, Completer, Completion, ThreadedCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory

from acli_py.domain.jql import Completer as QueryCompleter
from acli_py.domain.jql.catalog import Catalog, Value
from acli_py.domain.jql.smart import terms, unquote

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from pathlib import Path

    from prompt_toolkit.document import Document

Command = Any  # Typer's click objects (Typer bundles its own click)

# Which site values complete which parameter, by the parameter's name.
VALUE_SOURCES = {
    "project": "project",
    "status": "status",
    "issue_type": "issuetype",
    "label": "labels",
    "add_label": "labels",
    "remove_label": "labels",
    "priority": "priority",
    "component": "component",
    "fix_version": "fixVersion",
    "assignee": "assignee",
    "reporter": "assignee",
    "who": "assignee",
    "user": "assignee",
    "owner": "assignee",
    "lead": "assignee",
}
ISSUE_PARAMS = {"key", "keys", "source", "target", "parent", "issue"}
QUERY_PARAMS = {"jql", "query"}
META = {
    "help": "Show commands, or help for one: help issue create",
    "dry-run": "dry-run on | off: preview every change from now on",
    "tui": "Open the full-screen UI (optionally with a query)",
    "clear": "Clear the screen",
    "exit": "Leave the shell (or Ctrl+D)",
}
SECRET = re.compile(r"(?i)(--token(?!-stdin)\b|\s-t\s|token=)")


class SafeHistory(FileHistory):
    """Shell history that never writes down a line carrying a token."""

    def store_string(self, string: str) -> None:
        """Store `string` unless it looks like it holds a secret."""
        if not SECRET.search(f" {string} "):
            super().store_string(string)


NO_SHELL_OPTIONS = {"install_completion", "show_completion", "help"}


def _params(command: Command) -> list[Any]:
    return [
        p
        for p in command.params
        if not getattr(p, "hidden", False) and p.name not in NO_SHELL_OPTIONS
    ]


def _option(command: Command, name: str) -> Any | None:
    return next(
        (p for p in command.params if p.param_type_name == "option" and name in p.opts), None
    )


def _takes_value(param: Any) -> bool:
    return not (param.is_flag or getattr(param, "count", False))


class ShellCompleter(Completer):
    """Completes `acli-py` command lines."""

    def __init__(self, root: Command, catalog: Catalog) -> None:
        self.root = root
        self.catalog = catalog
        self.queries = QueryCompleter(catalog)

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterator[Completion]:
        """Yield completions for the text before the cursor."""
        text = document.text_before_cursor
        words = terms(text)
        if words and (not text[-1:].isspace() or _open_quote(words[-1].text)):
            current, done = words[-1].text, words[:-1]
        else:
            current, done = "", words
        args = [unquote(w.text) for w in done]
        if args and args[0] == "acli-py":
            args = args[1:]
        yield from self._complete(args, current)

    def _complete(self, args: list[str], current: str) -> Iterator[Completion]:
        command, rest = self._walk(args)
        if hasattr(command, "commands"):
            if current.startswith("-"):
                yield from self._options(command, current)
                return
            names = [(n, c) for n, c in command.commands.items() if not c.hidden and n != "shell"]
            for name, sub in sorted(names):
                if name.startswith(current):
                    yield Completion(name, -len(current), display_meta=_short(sub.help))
            if command is self.root and not args:
                for name, meta in META.items():
                    if name.startswith(current):
                        yield Completion(name, -len(current), display_meta=meta)
            return
        # A command: the value of an option, an option, or an argument.
        if rest:
            previous = _option(command, rest[-1])
            if previous is not None and _takes_value(previous):
                yield from self._values(previous, current, command)
                return
        if current.startswith("-"):
            yield from self._options(command, current)
            return
        argument = self._argument_at(command, rest)
        found = list(self._values(argument, current, command)) if argument is not None else []
        yield from found
        if not found and not current:
            yield from self._options(command, current)

    def _walk(self, args: list[str]) -> tuple[Command, list[str]]:
        """Follow the command names in `args`; return the command and what follows it."""
        command = self.root
        index = 0
        while index < len(args) and hasattr(command, "commands"):
            arg = args[index]
            if arg.startswith("-"):
                option = _option(command, arg)
                index += 2 if option is not None and _takes_value(option) else 1
                continue
            sub = command.commands.get(arg)
            if sub is None:
                break
            command = sub
            index += 1
        return command, args[index:]

    def _argument_at(self, command: Command, rest: list[str]) -> Any | None:
        """Return the positional parameter the next word fills."""
        positional = 0
        skip = False
        for word in rest:
            if skip:
                skip = False
                continue
            if word.startswith("-"):
                option = _option(command, word)
                skip = option is not None and _takes_value(option)
                continue
            positional += 1
        arguments = [p for p in command.params if p.param_type_name == "argument"]
        for argument in arguments:
            if argument.nargs == -1:
                return argument
            if positional == 0:
                return argument
            positional -= 1
        return None

    def _options(self, command: Command, current: str) -> Iterator[Completion]:
        for param in _params(command):
            if param.param_type_name != "option":
                continue
            # Offer the long name, or the short one when that is what is being typed.
            for name in sorted(param.opts, key=len, reverse=True):
                if name.startswith(current):
                    yield Completion(name, -len(current), display_meta=_short(param.help))
                    break

    def _values(self, param: Any, current: str, command: Command) -> Iterator[Completion]:
        name = param.name or ""
        choices = getattr(param.type, "choices", None)
        if choices:
            for choice in choices:
                value = str(getattr(choice, "value", choice))
                if value.startswith(current):
                    yield Completion(value, -len(current))
            return
        if name in QUERY_PARAMS:
            yield from self._query(current)
            return
        typed = unquote(current)
        if name in ISSUE_PARAMS:
            prefix = typed.rpartition(",")[2]
            yield from self._site_values(self.catalog.issues(prefix), current, prefix, "issue")
            return
        source = VALUE_SOURCES.get(name)
        if name == "to":  # `issue transition --to` takes a status; `assign`, `owner` a person
            source = "status" if command.name in ("transition", "move") else "assignee"
        if source:
            values = self.catalog.values(source, typed)
            if source == "assignee":
                values = [Value(v.display or v.value, v.value) for v in values]
                if "@me".startswith(typed.lower()):
                    values.insert(0, Value("@me", "you"))
            yield from self._site_values(values, current, typed, source)

    def _site_values(
        self, values: list[Value], current: str, typed: str, kind: str
    ) -> Iterator[Completion]:
        for value in values[:50]:
            text = value.value
            shown = shlex.quote(text) if re.search(r"[\s'\"]", text) else text
            if current and not current.startswith(("'", '"')) and "," in current:
                shown = current.rpartition(",")[0] + "," + shown
            meta = value.display if value.display != value.value else ""
            yield Completion(shown, -len(current), display=text, display_meta=meta or kind)

    def _query(self, current: str) -> Iterator[Completion]:
        quote = current[:1] if current[:1] in "'\"" else ""
        body = current[len(quote) :]
        found = self.queries.complete(body)
        for item in found.items:
            replaced = body[: found.start] + item.text
            yield Completion(
                (quote or "'") + replaced,
                -len(current),
                display=item.display,
                display_meta=item.meta or item.kind,
            )


def _open_quote(word: str) -> bool:
    """Return whether `word` opens a quote it doesn't close."""
    if word[:1] not in "'\"":
        return False
    body = re.sub(r"\\.", "", word[1:])
    return word[0] not in body


def _short(text: str | None) -> str:
    first = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return re.sub(r"\[/?[a-z ]*\]", "", first)[:70]


class Shell:
    """The read-run loop."""

    def __init__(
        self,
        root: Command,
        catalog: Catalog,
        *,
        history: Path,
        account: str,
        dry_run: bool = False,
        open_tui: Callable[[str], None] | None = None,
        output: Callable[[str], None] = print,
    ) -> None:
        self.root = root
        self.account = account
        self.dry_run = dry_run
        self.open_tui = open_tui
        self.say = output
        self.completer = ShellCompleter(root, catalog)
        self.history_path = history

    def toolbar(self) -> HTML:
        """Return the bottom bar: who, dry run, and hints."""
        mode = (
            "<style bg='ansimagenta' fg='ansiwhite'> DRY RUN </style>"
            if self.dry_run
            else "<b>live</b>"
        )
        return HTML(
            f" {self.account} │ {mode} │ Tab completes · → takes the grey suggestion · "
            "<b>help</b> · <b>tui</b> · <b>exit</b>"
        )

    def prompt(self) -> str:
        """Return the prompt text."""
        return "acli-py (dry run)> " if self.dry_run else "acli-py> "

    def run(self) -> None:
        """Read and run commands until exit or Ctrl+D."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        session: PromptSession[str] = PromptSession(
            history=SafeHistory(str(self.history_path)),
            completer=ThreadedCompleter(self.completer),
            auto_suggest=AutoSuggestFromHistory(),
            complete_while_typing=True,
            bottom_toolbar=self.toolbar,
        )
        self.say(
            "acli-py shell: type a command without 'acli-py'. Tab completes; 'help' lists commands."
        )
        while True:
            try:
                line = session.prompt(self.prompt())
            except KeyboardInterrupt:
                continue
            except EOFError:
                return
            if self.execute(line) == "exit":
                return

    def execute(self, line: str) -> str | int | None:
        """Run one line; return "exit" to leave, else the command's exit code."""
        line = line.strip()
        if not line or line.startswith("#"):
            return None
        try:
            args = shlex.split(line)
        except ValueError as error:
            self.say(f"Can't read that line: {error}")
            return 2
        if args[0] == "acli-py":
            args = args[1:]
        if not args:
            return None
        head = args[0]
        if head in ("exit", "quit"):
            return "exit"
        if head == "clear":
            self.say("\033[2J\033[H")
            return None
        if head == "dry-run":
            wanted = (args[1:] or ["toggle"])[0].lower()
            self.dry_run = {"on": True, "off": False}.get(wanted, not self.dry_run)
            self.say(f"Dry run is {'on: changes are only shown' if self.dry_run else 'off'}.")
            return None
        if head == "tui":
            if self.open_tui:
                self.open_tui(" ".join(args[1:]))
            return None
        if head == "shell":
            self.say("You are in the shell already.")
            return None
        if head == "help":
            args = [*args[1:], "--help"]
        return self.invoke(args)

    def invoke(self, args: list[str]) -> int:
        """Run an `acli-py` command in-process and return its exit code."""
        full = (["--dry-run"] if self.dry_run else []) + args
        try:
            result = self.root.main(full, prog_name="acli-py", standalone_mode=False)
        except SystemExit as leaving:
            return int(leaving.code or 0) if isinstance(leaving.code, int) else 1
        except Exception as error:  # click's own errors: show them like the CLI would
            show = getattr(error, "show", None)
            if callable(show):
                show()
                return int(getattr(error, "exit_code", 1))
            if type(error).__name__ == "Abort":
                self.say("Aborted.")
                return 1
            raise
        return int(result) if isinstance(result, int) else 0


def commands(root: Command) -> Iterable[str]:
    """Return every runnable command path, e.g. 'issue comment add' (for tests and docs)."""

    def walk(command: Command, path: list[str]) -> Iterator[str]:
        for name, sub in command.commands.items():
            if sub.hidden:
                continue
            if hasattr(sub, "commands"):
                yield from walk(sub, [*path, name])
            else:
                yield " ".join([*path, name])

    return list(walk(root, []))
