"""The TUI's own widgets: the query bar with its completion menu, and the list's cells."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.text import Text
from textual import events, on
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.suggester import SuggestionReady
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from acli_py.domain.values import ago as ago
from acli_py.domain.values import text as field_text
from acli_py.presentation.output import dig

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from acli_py.domain.jql import Completer, Completion, Suggestion

KIND_STYLE = {
    "field": "cyan",
    "operator": "yellow",
    "value": "green",
    "function": "magenta",
    "keyword": "bold blue",
    "filter": "cyan",
    "flag": "magenta",
    "issue": "bold green",
}
PRIORITY_GLYPH = {"highest": "⇈", "high": "↑", "medium": "=", "low": "↓", "lowest": "⇊"}
CATEGORY_STYLE = {"new": "bold white on grey30", "indeterminate": "bold black on dodger_blue1",
                  "done": "bold black on green3"}  # fmt: skip


# ── rendering helpers ────────────────────────────────────────────────────────


def status_cell(status: dict | None) -> Text:
    """Return a status as a coloured badge."""
    if not status:
        return Text("")
    category = dig(status, "statusCategory", "key", default="")
    return Text(f" {status.get('name', '')} ", style=CATEGORY_STYLE.get(category, "bold"))


TYPE_BADGE = {
    "bug": ("B", "bold red"),
    "story": ("S", "bold green"),
    "task": ("T", "bold blue"),
    "epic": ("E", "bold magenta"),
    "subtask": ("↳", "cyan"),
    "sub-task": ("↳", "cyan"),
}


def type_cell(issue_type: dict | None) -> Text:
    """Return an issue type as a one-letter coloured badge."""
    name = str((issue_type or {}).get("name") or "")
    letter, style = TYPE_BADGE.get(name.lower(), (name[:1].upper(), "bold"))
    if (issue_type or {}).get("subtask"):
        letter, style = TYPE_BADGE["subtask"]
    return Text(letter, style=style)


def priority_cell(priority: dict | None) -> Text:
    """Return a priority as an arrow, coloured by urgency."""
    name = str((priority or {}).get("name") or "")
    glyph: str = PRIORITY_GLYPH.get(name.lower(), name[:1])
    style = {"⇈": "bold red", "↑": "red", "=": "yellow", "↓": "green", "⇊": "dim green"}
    return Text(glyph, style=style.get(glyph, ""))


# ── the query bar ────────────────────────────────────────────────────────────


class CompletionMenu(OptionList):
    """The drop-down under the query input."""

    DEFAULT_CSS = """
    CompletionMenu {
        display: none;
        overlay: screen;
        constrain: none inside;
        max-height: 12;
        width: auto;
        min-width: 24;
        max-width: 72;
        border: round $accent;
        background: $surface;
        padding: 0;
    }
    CompletionMenu.-open { display: block; }
    """


class QueryInput(Input):
    """The query input: Tab accepts a completion, ↑/↓ move through them."""

    BINDINGS = [
        Binding("tab", "accept", "Complete", show=False, priority=True),
        Binding("down", "menu(1)", "Next suggestion", show=False),
        Binding("up", "menu(-1)", "Previous suggestion", show=False),
        Binding("ctrl+space", "open_menu", "Suggest", show=False),
        Binding("escape", "leave", "Back to the list", show=False),
    ]

    class Accept(Message):
        """Accept the highlighted completion."""

    class Move(Message):
        """Move the highlight in the menu."""

        def __init__(self, step: int) -> None:
            super().__init__()
            self.step = step

    class Leave(Message):
        """Close the menu, or leave the bar."""

    class Reopen(Message):
        """Show the completion menu again."""

    def action_accept(self) -> None:
        """Accept a completion."""
        self.post_message(self.Accept())

    def action_menu(self, step: int) -> None:
        """Move in the menu."""
        self.post_message(self.Move(step))

    def action_open_menu(self) -> None:
        """Show the menu."""
        self.post_message(self.Reopen())

    def action_leave(self) -> None:
        """Close the menu or leave."""
        self.post_message(self.Leave())


class QueryBar(Vertical):
    """A query input with live completion, and a line showing the JQL it runs."""

    DEFAULT_CSS = """
    QueryBar { height: auto; padding: 0 1; }
    QueryBar QueryInput { border: tall $accent; }
    QueryBar QueryInput:focus { border: tall $accent-lighten-2; }
    QueryBar #jql { height: 1; color: $text-muted; padding: 0 1; }
    QueryBar #jql.-error { color: $error; }
    """

    class Submitted(Message):
        """The user ran a query."""

        def __init__(self, query: str) -> None:
            super().__init__()
            self.query = query

    class Left(Message):
        """The user left the bar (Esc with no menu open)."""

    def __init__(self, completer: Completer, *, value: str = "", id: str | None = None) -> None:
        super().__init__(id=id)
        self.completer = completer
        self.initial = value
        self.completion: Completion | None = None
        self.menu_open = False
        self._generation = 0

    def compose(self) -> ComposeResult:
        """Lay out the input, the menu and the JQL line."""
        yield QueryInput(
            value=self.initial,
            placeholder="Search: @me #label s:status is:open text…  or JQL   (Tab completes)",
            id="query",
        )
        yield CompletionMenu(id="menu")
        yield Static("", id="jql")

    @property
    def input(self) -> QueryInput:
        """Return the input."""
        return self.query_one(QueryInput)

    @property
    def menu(self) -> CompletionMenu:
        """Return the menu."""
        return self.query_one(CompletionMenu)

    @property
    def value(self) -> str:
        """Return the query text."""
        return self.input.value

    @value.setter
    def value(self, text: str) -> None:
        self.input.value = text
        self.input.cursor_position = len(text)

    def show_jql(self, text: str, *, error: bool = False) -> None:
        """Show the JQL (or what's wrong with the query) under the input."""
        line = self.query_one("#jql", Static)
        line.update(Text(text, no_wrap=True, overflow="ellipsis"))
        line.set_class(error, "-error")

    # ── completion ───────────────────────────────────────────────────────────

    @on(Input.Changed, "#query")
    def _changed(self, event: Input.Changed) -> None:
        event.stop()
        self.refresh_completions(open_menu=self.input.has_focus)

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        """Offer completions as soon as the bar gets focus."""
        if isinstance(event.widget, QueryInput):
            self.refresh_completions(open_menu=True)

    def on_descendant_blur(self, event: events.DescendantBlur) -> None:
        """Hide the menu when focus goes elsewhere."""
        self.close_menu()

    def refresh_completions(self, *, open_menu: bool) -> None:
        """Compute completions for the text at the cursor (on a worker thread)."""
        self._generation += 1
        self._complete(self._generation, self.input.value, self.input.cursor_position, open_menu)

    def _complete(self, generation: int, text: str, cursor: int, open_menu: bool) -> None:
        # The catalog may ask Jira, so completion runs off the UI thread; only the newest
        # request's answer is shown.
        def work() -> None:
            found = self.completer.complete(text, cursor)
            self.app.call_from_thread(self._show, generation, found, open_menu)

        self.run_worker(work, thread=True, group="complete", exclusive=True, exit_on_error=False)

    def _show(self, generation: int, found: Completion, open_menu: bool) -> None:
        if generation != self._generation:
            return
        self.completion = found
        menu = self.menu
        menu.clear_options()
        menu.add_options(_option(item) for item in found.items)
        if found.items:
            menu.highlighted = 0
        if open_menu and found.items and self.input.has_focus:
            self.open_menu()
        else:
            self.close_menu()
        # Ghost text: the rest of the best completion, when it only adds to the end.
        value = self.input.value
        if found.items and found.end == len(value):
            new, _ = found.apply(value, found.items[0])
            if new.startswith(value) and len(new) > len(value):
                self.input.post_message(SuggestionReady(value, new))

    def open_menu(self) -> None:
        """Show the menu under the input."""
        self.menu_open = True
        self.menu.add_class("-open")
        self.menu.styles.offset = (min(self.input.cursor_screen_offset.x - 2, 40), 0)

    def close_menu(self) -> None:
        """Hide the menu."""
        self.menu_open = False
        self.menu.remove_class("-open")

    def accept(self, item: Suggestion | None = None) -> bool:
        """Insert `item` (default: the highlighted one); return whether anything was."""
        found = self.completion
        if found is None or not found.items:
            return False
        if item is None:
            index = self.menu.highlighted or 0
            item = found.items[min(index, len(found.items) - 1)]
        text, cursor = found.apply(self.input.value, item)
        self.input.value = text
        self.input.cursor_position = cursor
        return True

    @on(QueryInput.Accept)
    def _accept(self, event: QueryInput.Accept) -> None:
        event.stop()
        if not self.accept():
            self.app.action_focus_next()

    @on(QueryInput.Move)
    def _move(self, event: QueryInput.Move) -> None:
        event.stop()
        if not self.menu_open:
            self.refresh_completions(open_menu=True)
            return
        count = self.menu.option_count
        if count:
            self.menu.highlighted = ((self.menu.highlighted or 0) + event.step) % count

    @on(QueryInput.Reopen)
    def _reopen(self, event: QueryInput.Reopen) -> None:
        event.stop()
        self.refresh_completions(open_menu=True)

    @on(QueryInput.Leave)
    def _leave(self, event: QueryInput.Leave) -> None:
        event.stop()
        if self.menu_open:
            self.close_menu()
        else:
            self.post_message(self.Left())

    @on(OptionList.OptionSelected, "#menu")
    def _clicked(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if self.completion and event.option_index < len(self.completion.items):
            self.accept(self.completion.items[event.option_index])
        self.input.focus()

    @on(Input.Submitted, "#query")
    def _submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.close_menu()
        self.post_message(self.Submitted(self.input.value))


def _option(item: Suggestion) -> Option:
    label = Text(item.display, style=KIND_STYLE.get(item.kind, ""))
    if item.meta:
        label.append("  ")
        label.append(item.meta, style="dim")
    return Option(label)


def plain(value: Any) -> str:
    """Return a value as table text."""
    return field_text(value)
