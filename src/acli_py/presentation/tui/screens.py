"""Modal screens: pickers, editors, the new-issue form, help and the activity log."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from rich.text import Text
from textual import on, work
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    Label,
    Markdown,
    OptionList,
    Select,
    TextArea,
)
from textual.widgets.option_list import Option

from acli_py.domain.jql.catalog import matches
from acli_py.domain.jql.smart import cheatsheet

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from textual.app import ComposeResult

T = TypeVar("T")

MODAL_CSS = """
ModalScreen { align: center middle; background: $background 60%; }
ModalScreen > Vertical {
    width: 76; max-width: 95%; height: auto; max-height: 90%;
    border: round $accent; background: $surface; padding: 1 2;
}
ModalScreen .title { text-style: bold; color: $accent; padding-bottom: 1; }
ModalScreen .hint { color: $text-muted; padding-top: 1; }
ModalScreen OptionList { height: auto; max-height: 20; border: none; }
ModalScreen TextArea { height: 12; }
"""


@dataclass(frozen=True)
class Choice(Generic[T]):
    """One entry of a picker."""

    label: str
    value: T
    hint: str = ""


class PickScreen(ModalScreen[T | None]):
    """Pick one choice; type to filter. `search` (optional) fetches choices for the text."""

    SCOPED_CSS = False

    DEFAULT_CSS = MODAL_CSS
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("down", "move(1)", show=False),
        Binding("up", "move(-1)", show=False),
    ]

    def __init__(
        self,
        title: str,
        choices: list[Choice[T]],
        *,
        search: Callable[[str], Awaitable[list[Choice[T]]]] | None = None,
        placeholder: str = "Type to filter",
    ) -> None:
        super().__init__()
        self.heading = title
        self.choices = choices
        self.shown: list[Choice[T]] = []
        self.search = search
        self.placeholder = placeholder

    def compose(self) -> ComposeResult:
        """Lay out the filter and the list."""
        with Vertical():
            yield Label(self.heading, classes="title")
            yield Input(placeholder=self.placeholder, id="filter")
            yield OptionList(id="choices")
            yield Label("Enter picks · Esc cancels", classes="hint")

    def on_mount(self) -> None:
        """Show every choice."""
        self._fill(self.choices, "")

    def _fill(self, choices: list[Choice[T]], text: str) -> None:
        self.shown = [c for c in choices if matches(c.label, text) or matches(c.hint, text)]
        options = self.query_one("#choices", OptionList)
        options.clear_options()
        for choice in self.shown:
            label = Text(choice.label, style="bold")
            if choice.hint:
                label.append(f"  {choice.hint}", style="dim")
            options.add_option(Option(label))
        if self.shown:
            options.highlighted = 0

    @on(Input.Changed, "#filter")
    def _filter(self, event: Input.Changed) -> None:
        if self.search:
            self._search(event.value)
        else:
            self._fill(self.choices, event.value)

    @work(exclusive=True, group="search")
    async def _search(self, text: str) -> None:
        assert self.search is not None
        found = await self.search(text)
        if self.query_one("#filter", Input).value == text:
            self.choices = found
            self._fill(found, "")

    def action_move(self, step: int) -> None:
        """Move the highlight."""
        options = self.query_one("#choices", OptionList)
        if options.option_count:
            options.highlighted = ((options.highlighted or 0) + step) % options.option_count

    @on(Input.Submitted, "#filter")
    def _submit(self) -> None:
        index = self.query_one("#choices", OptionList).highlighted
        if index is not None and index < len(self.shown):
            self.dismiss(self.shown[index].value)

    @on(OptionList.OptionSelected, "#choices")
    def _picked(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self.shown[event.option_index].value)

    def action_cancel(self) -> None:
        """Close without picking."""
        self.dismiss(None)


class PromptScreen(ModalScreen[str | None]):
    """Ask for one line of text."""

    SCOPED_CSS = False

    DEFAULT_CSS = MODAL_CSS
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, value: str = "", *, hint: str = "Enter saves · Esc cancels"):
        super().__init__()
        self.heading, self.value, self.hint = title, value, hint

    def compose(self) -> ComposeResult:
        """Lay out the input."""
        with Vertical():
            yield Label(self.heading, classes="title")
            yield Input(value=self.value, id="value")
            yield Label(self.hint, classes="hint")

    @on(Input.Submitted, "#value")
    def _submit(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        """Close without saving."""
        self.dismiss(None)


class TextScreen(ModalScreen[str | None]):
    """Write Markdown: a comment or a description."""

    SCOPED_CSS = False

    DEFAULT_CSS = MODAL_CSS
    BINDINGS = [
        Binding("ctrl+s", "save", "Save", priority=True),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, title: str, value: str = "") -> None:
        super().__init__()
        self.heading, self.value = title, value

    def compose(self) -> ComposeResult:
        """Lay out the editor."""
        with Vertical():
            yield Label(self.heading, classes="title")
            yield TextArea(self.value, language="markdown", id="text", show_line_numbers=False)
            yield Label("Markdown · Ctrl+S saves · Esc cancels", classes="hint")

    def action_save(self) -> None:
        """Save, unless there is nothing written."""
        text = self.query_one("#text", TextArea).text
        if text.strip():
            self.dismiss(text)
        else:
            self.notify("Nothing written yet.", severity="warning")

    def action_cancel(self) -> None:
        """Close without saving."""
        self.dismiss(None)


@dataclass(frozen=True)
class NewIssue:
    """What the new-issue form collected."""

    project: str
    issue_type: str
    summary: str
    description: str
    assign_to_me: bool
    labels: tuple[str, ...]


class CreateScreen(ModalScreen[NewIssue | None]):
    """The new-issue form. `types_for(project)` lists a project's issue types."""

    SCOPED_CSS = False

    DEFAULT_CSS = (
        MODAL_CSS
        + """
    CreateScreen > Vertical { width: 90; }
    CreateScreen Horizontal { height: auto; }
    CreateScreen Select { width: 1fr; }
    CreateScreen Label.field { padding-top: 1; color: $text-muted; }
    CreateScreen #buttons { padding-top: 1; align-horizontal: right; }
    """
    )
    BINDINGS = [
        Binding("ctrl+s", "save", "Create", priority=True),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        projects: list[tuple[str, str]],
        types_for: Callable[[str], Awaitable[list[str]]],
        *,
        project: str | None = None,
    ) -> None:
        super().__init__()
        self.projects = projects
        self.types_for = types_for
        self.project = project if project in {k for k, _ in projects} else None

    def compose(self) -> ComposeResult:
        """Lay out the form."""
        with Vertical():
            yield Label("New issue", classes="title")
            with Horizontal():
                yield Select(
                    [(f"{name} ({key})", key) for key, name in self.projects],
                    prompt="Project",
                    value=self.project or Select.NULL,
                    id="project",
                )
                yield Select([], prompt="Type", id="type")
            yield Label("Summary", classes="field")
            yield Input(placeholder="One line that says what it is", id="summary")
            yield Label("Description (Markdown)", classes="field")
            yield TextArea("", language="markdown", id="description", show_line_numbers=False)
            yield Label("Labels (comma-separated)", classes="field")
            yield Input(id="labels")
            yield Checkbox("Assign to me", value=True, id="mine")
            with Horizontal(id="buttons"):
                yield Button("Create  ^S", variant="primary", id="create")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        """Load the types of the preselected project."""
        if self.project:
            self._load_types(self.project)
        self.query_one("#summary" if self.project else "#project").focus()

    @on(Select.Changed, "#project")
    def _project_changed(self, event: Select.Changed) -> None:
        if isinstance(event.value, str):
            self._load_types(event.value)

    @work(exclusive=True, group="types")
    async def _load_types(self, project: str) -> None:
        names = await self.types_for(project)
        select = self.query_one("#type", Select)
        select.set_options([(n, n) for n in names])
        preferred = next((n for n in ("Task", "Story", "Bug") if n in names), None)
        if preferred or names:
            select.value = preferred or names[0]

    @on(Button.Pressed, "#create")
    def action_save(self) -> None:
        """Create the issue if the form is complete."""
        project = self.query_one("#project", Select).value
        kind = self.query_one("#type", Select).value
        summary = self.query_one("#summary", Input).value.strip()
        missing = [
            name
            for name, value in (("project", project), ("type", kind), ("summary", summary))
            if not isinstance(value, str) or not value
        ]
        if missing:
            self.notify(f"Still needed: {', '.join(missing)}.", severity="warning")
            return
        labels = tuple(
            label.strip()
            for label in self.query_one("#labels", Input).value.replace(",", " ").split()
            if label.strip()
        )
        self.dismiss(
            NewIssue(
                str(project),
                str(kind),
                summary,
                self.query_one("#description", TextArea).text,
                self.query_one("#mine", Checkbox).value,
                labels,
            )
        )

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        """Close without creating."""
        self.dismiss(None)


KEYS = """
| Key | Does |
|---|---|
| `/` | Edit the query (Tab completes, ↑/↓ choose, → takes the grey suggestion) |
| `Enter` | Run the query · in the list: read the issue |
| `j` `k` `g` `G` | Down, up, first, last |
| `Space` | Mark or unmark an issue; `t` `a` `l` `p` then act on every marked one |
| `t` | Transition (move to another status) |
| `a` / `A` | Assign to someone / to me |
| `c` | Comment |
| `e` | Edit the summary |
| `d` | Edit the description |
| `l` | Add or remove labels (`web -legacy`) |
| `p` | Priority |
| `w` | Watch or unwatch |
| `n` | New issue |
| `o` | Open in the browser |
| `y` / `Y` | Copy the key / the link |
| `S` | Sort by… |
| `s` | Save the query as a view |
| `v` | Jump to the views |
| `r` | Refresh |
| `L` | Activity log (and what a dry run planned) |
| `Ctrl+P` | Command palette |
| `q` | Quit |
"""


class HelpScreen(ModalScreen[None]):
    """Keys, and the smart query syntax."""

    SCOPED_CSS = False

    DEFAULT_CSS = (
        MODAL_CSS
        + """
    HelpScreen > VerticalScroll {
        width: 100; max-width: 95%; height: 90%;
        border: round $accent; background: $surface; padding: 0 2;
    }
    """
    )
    BINDINGS = [Binding("escape,q,question_mark", "close", "Close")]

    def compose(self) -> ComposeResult:
        """Render the help."""
        rows = "\n".join(
            f"| `{term}` | {aliases} | {meaning} |" for term, aliases, meaning in cheatsheet()
        )
        text = (
            "# acli-py · keys\n"
            + KEYS
            + "\n# Smart queries\n\nTerms combine with AND; a filter given twice means either. "
            "Anything with `=`, `~`, `in (` or `ORDER BY` is run as JQL, with completion too.\n\n"
            "| Term | Also | Meaning |\n|---|---|---|\n" + rows + "\n"
        )
        with VerticalScroll():
            yield Markdown(text)

    def action_close(self) -> None:
        """Close the help."""
        self.dismiss(None)


class ActivityScreen(ModalScreen[None]):
    """Every query and command sent, newest first, and the writes a dry run planned."""

    SCOPED_CSS = False

    DEFAULT_CSS = (
        MODAL_CSS
        + """
    ActivityScreen > Vertical { width: 120; max-width: 98%; height: 90%; }
    ActivityScreen DataTable { height: 1fr; }
    """
    )
    BINDINGS = [Binding("escape,q,L", "close", "Close")]

    def __init__(self, entries: list[Any], plans: list[Any]) -> None:
        super().__init__()
        self.entries, self.plans = entries, plans

    def compose(self) -> ComposeResult:
        """Lay out the log."""
        with Vertical():
            yield Label("Activity", classes="title")
            yield DataTable(id="log", zebra_stripes=True, cursor_type="row")
            if self.plans:
                yield Label(f"Dry run: {len(self.plans)} planned writes", classes="title")
                yield DataTable(id="plans", cursor_type="row")

    def on_mount(self) -> None:
        """Fill the tables."""
        log = self.query_one("#log", DataTable)
        log.add_columns("Time", "Message", "ms", "Details")
        for entry in reversed(self.entries):
            took = f"{entry.seconds * 1000:.0f}"
            detail = Text(entry.error, style="red") if entry.error else Text(entry.summary)
            log.add_row(datetime.fromtimestamp(entry.at).strftime("%H:%M:%S"), entry.name, took,
                        detail)  # fmt: skip
        if self.plans:
            plans = self.query_one("#plans", DataTable)
            plans.add_columns("Method", "Path", "Body")
            for plan in self.plans:
                plans.add_row(plan.method, plan.path, Text(str(plan.body)[:200]))

    def action_close(self) -> None:
        """Close the log."""
        self.dismiss(None)
