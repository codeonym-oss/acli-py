"""`acli-py tui`: browse, search and change issues without leaving the terminal.

Every read and write goes through the mediator (`acli_py.application.bus`), so the UI never blocks:
queries are cached for a minute, and each command empties the cache and announces the issue
it changed, which refreshes that row. In a dry run nothing is written; the activity log (L)
shows what would have been.
"""

from __future__ import annotations

import asyncio
import re
import webbrowser
from typing import TYPE_CHECKING, Any

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import DataTable, Footer, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from acli_py.application.bulk import TooManyError
from acli_py.application.changes import Change, Declined
from acli_py.application.commands.assign_issue.command import AssignIssue
from acli_py.application.commands.edit_issue.command import EditIssue
from acli_py.application.commands.transition_issue.command import TransitionIssue
from acli_py.application.commands.watch_issue.command import WatchIssue
from acli_py.application.messages import (
    CommentOnIssue,
    CountIssues,
    CreateIssue,
    FindAssignees,
    GetTransitions,
    ListFilters,
    ListIssueTypes,
    ListPriorities,
    ListProjects,
    SearchIssues,
    ValidateJql,
)
from acli_py.application.queries.get_issue.query import GetIssue
from acli_py.domain import adf
from acli_py.domain.jql import Completer, compile_query
from acli_py.domain.jql.catalog import Catalog, spelling
from acli_py.domain.jql.smart import looks_like_jql, terms
from acli_py.infrastructure.jira.client import JiraError, PlannedRequest
from acli_py.infrastructure.jira.resolve import ResolveError
from acli_py.infrastructure.storage import History, Views
from acli_py.presentation.output import dig
from acli_py.presentation.tui.screens import (
    ActivityScreen,
    Choice,
    ConfirmScreen,
    CreateScreen,
    HelpScreen,
    PickScreen,
    PromptScreen,
    TextScreen,
)
from acli_py.presentation.tui.widgets import (
    QueryBar,
    ago,
    priority_cell,
    status_cell,
    type_cell,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from textual.screen import Screen

    from acli_py.application.bus import Bus
    from acli_py.application.events.issue_changed.event import IssueChanged

FALLBACK_WHERE = "updated >= -30d"  # Jira refuses a search with no condition at all
SORTS = [
    ("-updated", "Recently updated first"),
    ("-created", "Newest first"),
    ("-priority", "Highest priority first"),
    ("status", "By status"),
    ("due", "Due soonest"),
    ("key", "By key"),
    ("rank", "Board rank"),
    ("assignee", "By assignee"),
]
ERRORS = (JiraError, ResolveError, ValueError)
SUMMARY = "summary"
# (label, key, width): the key column fits the keys, and the summary takes what is left.
COLUMNS = (
    ("", "mark", 1),
    ("Key", "key", None),
    ("T", "type", 1),
    ("Status", "status", 12),
    ("P", "priority", 1),
    ("Assignee", "assignee", 13),
    ("Age", "updated", 4),
    ("Summary", SUMMARY, None),
)


class AskInModal:
    """The TUI's way to ask before a change: a y/n modal over the screen."""

    def __init__(self, app: App[Any]) -> None:
        self.app = app

    async def confirm(self, change: Change) -> bool:
        """Show the change and wait for the answer (commands are sent from workers)."""
        return bool(await self.app.push_screen_wait(ConfirmScreen(f"{change}?", change.preview)))


class IssueBrowser(App[None]):
    """The TUI."""

    TITLE = "acli-py"
    CSS = """
    Screen { layout: vertical; }
    #top { height: 1; background: $primary-background; color: $text; padding: 0 1; }
    #main { height: 1fr; }
    #views { width: 28; border: round $panel; }
    #views:focus { border: round $accent; }
    #issues { width: 3fr; height: 1fr; border: round $panel; overflow-x: hidden; }
    #issues:focus { border: round $accent; }
    #detail-box { width: 2fr; min-width: 40; border: round $panel; padding: 0 1; }
    #detail-box:focus-within { border: round $accent; }
    #status { height: 1; padding: 0 1; color: $text-muted; }
    Screen.-narrow #views { display: none; }
    Screen.-tiny #detail-box { display: none; }
    """
    BINDINGS = [
        Binding("slash", "focus_query", "Query"),
        Binding("question_mark", "help", "Help"),
        Binding("t", "transition", "Transition"),
        Binding("a", "assign", "Assign"),
        Binding("A", "assign_me", "Take it", show=False),
        Binding("c", "comment", "Comment"),
        Binding("e", "edit_summary", "Summary", show=False),
        Binding("d", "edit_description", "Description", show=False),
        Binding("l", "labels", "Labels", show=False),
        Binding("p", "priority", "Priority", show=False),
        Binding("w", "watch", "Watch", show=False),
        Binding("n", "new", "New"),
        Binding("o", "open", "Browser"),
        Binding("y", "copy(False)", "Copy key", show=False),
        Binding("Y", "copy(True)", "Copy link", show=False),
        Binding("space", "mark", "Mark", show=False),
        Binding("x", "clear_marks", "Unmark all", show=False),
        Binding("S", "sort", "Sort", show=False),
        Binding("s", "save_view", "Save view", show=False),
        Binding("v", "focus_views", "Views", show=False),
        Binding("r", "refresh", "Refresh"),
        Binding("L", "activity", "Log", show=False),
        Binding("j", "cursor(1)", show=False),
        Binding("k", "cursor(-1)", show=False),
        Binding("g", "cursor_edge(False)", show=False),
        Binding("G", "cursor_edge(True)", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        bus: Bus,
        catalog: Catalog,
        *,
        query: str = "",
        default_project: str | None = None,
        views: Views | None = None,
        history: History | None = None,
    ) -> None:
        super().__init__()
        self.bus = bus
        self.site = bus.site
        self.catalog = catalog
        self.completer = Completer(catalog)
        self.default_project = default_project
        self.views = views or Views()
        self.history = history or History()
        self.first_query = query or self.views.all()[0].query
        self.rows: list[dict] = []
        self.marked: list[str] = []
        self.jql = ""
        self.next_token: str | None = None
        self.loading_more = False
        self.total: int | None = None
        self.filters: list[dict] = []
        self.plans: list[PlannedRequest] = []
        self.view_queries: list[str | None] = []
        self.site.client.on_plan = self._planned_from_thread
        bus.listeners.append(self._changed)
        bus.confirm.confirmer = AskInModal(self)
        bus.activity.listeners.append(self._show_busy)

    # ── layout ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        """Lay out the screen."""
        yield Static(self._top_text(), id="top")
        yield QueryBar(self.completer, value=self.first_query, id="bar")
        with Horizontal(id="main"):
            yield OptionList(id="views")
            yield DataTable(id="issues", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="detail-box"):
                yield Markdown("", id="detail")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the table and views, then run the first query."""
        table = self.query_one("#issues", DataTable)
        self._add_columns()
        self.query_one("#views", OptionList).border_title = "Views"
        table.border_title = "Issues"
        self.query_one("#detail-box").border_title = "Detail"
        self._fill_views()
        self._load_filters()
        self._fit(self.size.width)
        self.run_query()
        table.focus()

    def on_resize(self, event: Any) -> None:
        """Hide the sidebar, then the detail pane, as the terminal narrows."""
        self._fit(event.size.width)
        self.call_after_refresh(self._resize_columns)

    def _key_width(self) -> int:
        return max([len("Key"), *(len(r["key"]) for r in self.rows)])

    def _summary_width(self) -> int:
        fixed = sum(width + 2 for _, _, width in COLUMNS if width) + self._key_width() + 2
        return max(20, self.table.scrollable_content_region.width - fixed - 3)

    def _add_columns(self) -> None:
        for label, key, width in COLUMNS:
            if key == SUMMARY:
                width = self._summary_width()
            elif key == "key":
                width = self._key_width()
            self.table.add_column(label, key=key, width=width)

    def _resize_columns(self) -> None:
        column = self.table.columns.get(SUMMARY)  # type: ignore[call-overload]
        if column is not None and column.width != self._summary_width():
            self._render_rows()

    def _fit(self, width: int) -> None:
        self.screen.set_class(width < 130, "-narrow")
        self.screen.set_class(width < 90, "-tiny")

    def _top_text(self) -> Text:
        text = Text(" acli-py ", style="bold reverse")
        who = self.site.display_name or self.site.url
        text.append(f"  {who} · {self.site.url.split('://')[-1]}", style="bold")
        if self.site.dry_run:
            text.append("   DRY RUN ", style="bold white on magenta")
            text.append(" nothing is sent to Jira", style="magenta")
        busy = self.bus.activity.busy
        if busy:
            text.append(f"   ⟳ {busy}", style="bold yellow")
        return text

    def _show_busy(self) -> None:
        try:
            self.query_one("#top", Static).update(self._top_text())
        except Exception:
            return

    def status(self, message: str | Text) -> None:
        """Show a line at the bottom."""
        self.query_one("#status", Static).update(message)

    # ── views sidebar ────────────────────────────────────────────────────────

    def _fill_views(self) -> None:
        options: list[Option] = []
        self.view_queries = []

        def heading(name: str) -> None:
            options.append(Option(Text(name.upper(), style="bold dim"), disabled=True))
            self.view_queries.append(None)

        heading("Views")
        for view in self.views.all():
            options.append(Option(Text(("  " if view.builtin else "★ ") + view.name)))
            self.view_queries.append(view.query)
        if self.filters:
            heading("Favourite filters")
            for item in self.filters:
                options.append(Option(Text(f"⚑ {item.get('name', '?')}")))
                self.view_queries.append(item.get("jql") or f"filter = {item.get('id')}")
        recent = list(reversed(self.history.load()))[:8]
        if recent:
            heading("Recent")
            for query in recent:
                short = query if len(query) <= 22 else query[:21] + "…"
                options.append(Option(Text(f"↺ {short}")))
                self.view_queries.append(query)
        menu = self.query_one("#views", OptionList)
        menu.clear_options()
        menu.add_options(options)

    @work(group="filters")
    async def _load_filters(self) -> None:
        try:
            self.filters = await self.bus.send(ListFilters())
        except ERRORS:
            return
        self._fill_views()

    @on(OptionList.OptionSelected, "#views")
    def _view_chosen(self, event: OptionList.OptionSelected) -> None:
        query = self.view_queries[event.option_index]
        if query:
            self.bar.value = query
            self.run_query()
            self.query_one("#issues", DataTable).focus()

    # ── searching ────────────────────────────────────────────────────────────

    @property
    def bar(self) -> QueryBar:
        """Return the query bar."""
        return self.query_one(QueryBar)

    @property
    def table(self) -> DataTable:
        """Return the issue table."""
        return self.query_one("#issues", DataTable)

    @on(QueryBar.Submitted)
    def _submitted(self, event: QueryBar.Submitted) -> None:
        self.run_query()
        self.table.focus()

    @on(QueryBar.Left)
    def _left_bar(self) -> None:
        self.table.focus()

    @work(exclusive=True, group="search")
    async def run_query(self, keep: str | None = None) -> None:
        """Compile the query, check it with Jira, and show the first page."""
        text = self.bar.value.strip()
        try:
            compiled = await asyncio.to_thread(compile_query, text, resolve=spelling(self.catalog))
        except ValueError as error:
            self.bar.show_jql(f"✘ {error}", error=True)
            return
        where = compiled.where
        if not where:
            where = f"project = {self.default_project}" if self.default_project else FALLBACK_WHERE
        jql = f"{where} ORDER BY {compiled.order}" if compiled.order else where
        mode = "JQL" if compiled.mode == "jql" else "smart → JQL"
        self.bar.show_jql(f"{mode}: {jql}")
        for warning in compiled.warnings:
            self.notify(warning, severity="warning", timeout=6)
        try:
            problems = await self.bus.send(ValidateJql(jql))
            if problems:
                self.bar.show_jql("✘ " + " ".join(problems), error=True)
                return
            self.status(Text("Searching…", style="yellow"))
            page = await self.bus.send(SearchIssues(jql))
        except ERRORS as error:
            self.bar.show_jql(f"✘ {error}", error=True)
            self.status("")
            return
        self.jql, self.next_token, self.total = jql, page.next_token, None
        self.rows = list(page.issues)
        self.marked = [k for k in self.marked if any(r["key"] == k for r in self.rows)]
        self._render_rows(keep)
        if text and text not in self.history.load()[-8:]:
            self.history.add(text)
            self._fill_views()
        elif text:
            self.history.add(text)
        self._count(jql)
        if not self.rows:
            self.query_one("#detail", Markdown).update("_No issues match._")

    @work(exclusive=True, group="count")
    async def _count(self, jql: str) -> None:
        try:
            self.total = await self.bus.send(CountIssues(jql))
        except ERRORS:
            self.total = None
        self._show_count()

    def _show_count(self) -> None:
        shown = len(self.rows)
        total = self.total
        more = f" of ~{total}" if total is not None and total > shown else ""
        marks = f" · {len(self.marked)} marked (Space)" if self.marked else ""
        self.status(f"{shown}{more} issues{marks} · ? for help")
        self.table.border_title = f"Issues ({shown}{more})"

    def _render_rows(self, keep: str | None = None) -> None:
        table = self.table
        current = keep or self.current_key()
        table.clear(columns=True)
        self._add_columns()
        for issue in self.rows:
            table.add_row(*self._cells(issue), key=issue["key"])
        if current and any(r["key"] == current for r in self.rows):
            table.move_cursor(row=table.get_row_index(current))
        self._show_count()

    def _cells(self, issue: dict) -> list[Any]:
        f = issue.get("fields", {})
        mark = Text("●", style="bold magenta") if issue["key"] in self.marked else Text(" ")
        return [
            mark,
            Text(issue["key"], style="bold cyan"),
            type_cell(f.get("issuetype")),
            status_cell(f.get("status")),
            priority_cell(f.get("priority")),
            Text(
                dig(f, "assignee", "displayName", default="—"),
                style="" if f.get("assignee") else "dim",
            ),
            Text(ago(f.get("updated")), style="dim"),
            Text(f.get("summary", ""), no_wrap=True, overflow="ellipsis"),
        ]

    @work(exclusive=True, group="more")
    async def _load_more(self) -> None:
        if not self.next_token or self.loading_more:
            return
        self.loading_more = True
        try:
            page = await self.bus.send(SearchIssues(self.jql, token=self.next_token))
        except ERRORS as error:
            self.notify(str(error), severity="error")
            return
        finally:
            self.loading_more = False
        self.next_token = page.next_token
        known = {r["key"] for r in self.rows}
        for issue in page.issues:
            if issue["key"] not in known:
                self.rows.append(issue)
                self.table.add_row(*self._cells(issue), key=issue["key"])
        self._show_count()

    # ── the detail pane ──────────────────────────────────────────────────────

    def current_key(self) -> str | None:
        """Return the key of the highlighted issue."""
        table = self.table
        if not table.row_count or not 0 <= table.cursor_row < table.row_count:
            return None
        return str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)

    def current(self) -> dict | None:
        """Return the highlighted issue's row data."""
        key = self.current_key()
        return next((r for r in self.rows if r["key"] == key), None)

    @on(DataTable.RowHighlighted, "#issues")
    def _highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value:
            self._show_detail(str(event.row_key.value))
        if event.cursor_row >= len(self.rows) - 5 and self.next_token:
            self._load_more()

    @on(DataTable.RowSelected, "#issues")
    def _selected(self, event: DataTable.RowSelected) -> None:
        self.query_one("#detail-box").focus()

    @work(exclusive=True, group="detail")
    async def _show_detail(self, key: str, *, delay: float = 0.12) -> None:
        await asyncio.sleep(delay)  # let fast scrolling settle first
        try:
            view = await self.bus.send(GetIssue(key))
        except ERRORS as error:
            self.query_one("#detail", Markdown).update(f"**{key}**: {error}")
            return
        if key != self.current_key():
            return
        await self.query_one("#detail", Markdown).update(view.to_markdown())
        self.query_one("#detail-box").border_title = key

    # ── changes ──────────────────────────────────────────────────────────────

    def _planned_from_thread(self, plan: PlannedRequest) -> None:
        self.call_from_thread(self.plans.append, plan)

    async def _changed(self, change: IssueChanged) -> None:
        if change.dry_run:
            self.notify(
                f"Dry run: {change.what} on {change.key} planned, nothing sent (L shows it).",
                title="DRY RUN",
                severity="warning",
            )
            return
        if change.what == "CreateIssue":
            return
        try:
            page = await self.bus.send(SearchIssues(f"key in ({change.key})", size=1))
        except ERRORS:
            return
        fresh = next((i for i in page.issues if i["key"] == change.key), None)
        for index, row in enumerate(self.rows):
            if fresh and row["key"] == change.key:
                row["fields"].update(
                    {k: v for k, v in fresh["fields"].items() if k in row["fields"]}
                )
                self.rows[index] = row
                for column, value in zip(self.table.columns, self._cells(row), strict=True):
                    self.table.update_cell(change.key, column, value)
        if change.key == self.current_key():
            self._show_detail(change.key, delay=0)

    def targets(self) -> list[str]:
        """Return the marked issues, or else the highlighted one."""
        if self.marked:
            return list(self.marked)
        key = self.current_key()
        return [key] if key else []

    async def _each(
        self, keys: list[str], make: Any, done: str, change: Change | None = None
    ) -> None:
        """Run one command per key through the bulk engine, then say how it went.

        The engine asks once about `change` (by default, the one the commands make together),
        showing each issue's value now and after, and keeps going past failures.
        """
        try:
            report = await self.bus.bulk.run(
                [make(key) for key in keys], change=change, keep_going=True
            )
        except Declined:
            return
        except TooManyError as error:
            self.notify(str(error), severity="error")
            return
        if report.failed:
            failed = "\n".join(f"{o.key}: {o.error}" for o in report.failed)
            self.notify(failed, title="Failed", severity="error", timeout=10)
        ok = [o.key for o in report.succeeded]
        if ok and not self.site.dry_run:
            self.notify(f"{', '.join(ok) if len(ok) <= 3 else f'{len(ok)} issues'} {done}.")

    def action_mark(self) -> None:
        """Mark or unmark the highlighted issue."""
        key = self.current_key()
        if not key:
            return
        if key in self.marked:
            self.marked.remove(key)
        else:
            self.marked.append(key)
        row = next(r for r in self.rows if r["key"] == key)
        self.table.update_cell(key, "mark", self._cells(row)[0])
        self.action_cursor(1)
        self._show_count()

    def action_clear_marks(self) -> None:
        """Unmark everything."""
        self.marked.clear()
        self._render_rows()

    @work(group="action")
    async def action_transition(self) -> None:
        """Move the target issues to another status."""
        keys = self.targets()
        if not keys:
            return
        try:
            options = await asyncio.gather(*(self.bus.send(GetTransitions(k)) for k in keys))
        except ERRORS as error:
            self.notify(str(error), severity="error")
            return
        # Several issues: offer the statuses every one of them can reach.
        reachable = [{dig(t, "to", "name") for t in found} for found in options]
        common = set.intersection(*reachable) if reachable else set()
        choices = [
            Choice(f"{t['name']}", dig(t, "to", "name"), f"→ {dig(t, 'to', 'name')}")
            for t in options[0]
            if dig(t, "to", "name") in common
        ]
        if not choices:
            self.notify("No transition is available to all of them.", severity="warning")
            return
        title = f"Move {keys[0] if len(keys) == 1 else f'{len(keys)} issues'} to…"
        target = await self.push_screen_wait(PickScreen(title, choices))
        if not target:
            return
        await self._each(keys, lambda k: TransitionIssue(k, target), f"moved to {target}")

    @work(group="action")
    async def action_assign(self) -> None:
        """Assign the target issues to someone."""
        keys = self.targets()
        if not keys:
            return
        fixed: list[Choice[tuple[str | None, str]]] = [
            Choice("Me", (self.site.account_id or "@me", "me"), "assign to yourself"),
            Choice("Unassigned", (None, "nobody"), "clear the assignee"),
        ]

        async def search(text: str) -> list[Choice[tuple[str | None, str]]]:
            try:
                people = await self.bus.send(FindAssignees(keys[0], text))
            except ERRORS:
                people = []
            found = [
                Choice(
                    p.get("displayName", "?"),
                    (p["accountId"], p.get("displayName", "")),
                    p.get("emailAddress", ""),
                )
                for p in people
            ]
            return [c for c in fixed if not text or text.lower() in c.label.lower()] + found

        start = await search("")
        picked = await self.push_screen_wait(
            PickScreen("Assign to…", start, search=search, placeholder="Name or email")
        )
        if picked is None:
            return
        account, name = picked
        if account == "@me":
            account = await self._me()
            if account is None:
                return
        await self._each(keys, lambda k: AssignIssue(k, account, name), f"assigned to {name}")

    async def _me(self) -> str | None:
        """Return the user's account id, or say why it can't be known."""
        try:
            return await asyncio.to_thread(lambda: self.site.me)
        except ERRORS as error:
            self.notify(f"Couldn't tell who you are: {error}", severity="error")
            return None

    @work(group="action")
    async def action_assign_me(self) -> None:
        """Assign the target issues to yourself."""
        keys = self.targets()
        me = await self._me()
        if keys and me:
            await self._each(keys, lambda k: AssignIssue(k, me, "me"), "assigned to you")

    @work(group="action")
    async def action_comment(self) -> None:
        """Comment on the target issues."""
        keys = self.targets()
        if not keys:
            return
        title = f"Comment on {keys[0] if len(keys) == 1 else f'{len(keys)} issues'}"
        body = await self.push_screen_wait(TextScreen(title))
        if body:
            await self._each(keys, lambda k: CommentOnIssue(k, body), "commented")

    @work(group="action")
    async def action_edit_summary(self) -> None:
        """Change the highlighted issue's summary."""
        issue = self.current()
        if not issue:
            return
        old = dig(issue, "fields", "summary", default="")
        new = await self.push_screen_wait(PromptScreen(f"Summary of {issue['key']}", old))
        if new and new.strip() and new != old:
            await self._each(
                [issue["key"]], lambda k: EditIssue.setting(k, "summary", new.strip()), "renamed"
            )

    @work(group="action")
    async def action_edit_description(self) -> None:
        """Rewrite the highlighted issue's description."""
        key = self.current_key()
        if not key:
            return
        try:
            view = await self.bus.send(GetIssue(key))
        except ERRORS as error:
            self.notify(str(error), severity="error")
            return
        old = view.issue.description
        new = await self.push_screen_wait(TextScreen(f"Description of {key}", old))
        if new is not None and new != old:
            body = adf.to_adf(new)
            await self._each([key], lambda k: EditIssue.setting(k, "description", body), "updated")

    @work(group="action")
    async def action_labels(self) -> None:
        """Add and remove labels: `web -legacy`."""
        keys = self.targets()
        if not keys:
            return
        current = dig(self.current() or {}, "fields", "labels", default=[]) or []
        text = await self.push_screen_wait(
            PromptScreen(
                f"Labels for {keys[0] if len(keys) == 1 else f'{len(keys)} issues'}",
                "",
                hint=f"Now: {', '.join(current) or 'none'} · 'web -old' adds web, removes old",
            )
        )
        if not text:
            return
        words = text.replace(",", " ").split()
        add = tuple(w for w in words if not w.startswith("-"))
        remove = tuple(w[1:] for w in words if w.startswith("-") and len(w) > 1)
        await self._each(keys, lambda k: EditIssue.labelling(k, add, remove), "relabelled")

    @work(group="action")
    async def action_priority(self) -> None:
        """Set the priority."""
        keys = self.targets()
        if not keys:
            return
        try:
            priorities = await self.bus.send(ListPriorities())
        except ERRORS as error:
            self.notify(str(error), severity="error")
            return
        choices = [Choice(p["name"], p["name"], p.get("description", "")) for p in priorities]
        picked = await self.push_screen_wait(PickScreen("Priority", choices))
        if picked:
            await self._each(
                keys,
                lambda k: EditIssue.setting(k, "priority", {"name": picked}),
                f"set to {picked}",
            )

    @work(group="action")
    async def action_watch(self) -> None:
        """Watch the highlighted issue, or stop watching it."""
        key = self.current_key()
        if not key:
            return
        try:
            view = await self.bus.send(GetIssue(key))
        except ERRORS as error:
            self.notify(str(error), severity="error")
            return
        me = await self._me()
        if me is None:
            return
        watching = view.issue.watching
        await self._each(
            [key], lambda k: WatchIssue(k, me, not watching), "unwatched" if watching else "watched"
        )

    @work(group="action")
    async def action_new(self) -> None:
        """Create an issue."""
        try:
            projects = await self.bus.send(ListProjects())
        except ERRORS as error:
            self.notify(str(error), severity="error")
            return

        async def types_for(project: str) -> list[str]:
            try:
                return [t["name"] for t in await self.bus.send(ListIssueTypes(project))]
            except ERRORS:
                return ["Task"]

        current = dig(self.current() or {}, "key", default="")
        project = current.split("-")[0] if current else self.default_project
        form = CreateScreen(
            [(p["key"], p.get("name", p["key"])) for p in projects], types_for, project=project
        )
        new = await self.push_screen_wait(form)
        if not new:
            return
        try:
            key = await self.bus.send(
                CreateIssue(
                    new.project,
                    new.issue_type,
                    new.summary,
                    new.description,
                    new.assign_to_me,
                    new.labels,
                )
            )
        except ERRORS as error:
            self.notify(str(error), title="Not created", severity="error", timeout=10)
            return
        if self.site.dry_run:
            return
        self.notify(f"Created {key}.")
        self.run_query(keep=key)

    def action_open(self) -> None:
        """Open the highlighted issue in the browser."""
        if key := self.current_key():
            webbrowser.open(self.site.browse(key))

    def action_copy(self, link: bool) -> None:
        """Copy the key (or link) of the highlighted issue."""
        if key := self.current_key():
            text = self.site.browse(key) if link else key
            self.copy_to_clipboard(text)
            self.notify(f"Copied {text}")

    @work(group="action")
    async def action_sort(self) -> None:
        """Pick an order, and rewrite the query with it."""
        choices = [Choice(label, value, value) for value, label in SORTS]
        picked = await self.push_screen_wait(PickScreen("Sort by", choices))
        if picked:
            self.bar.value = with_order(self.bar.value, picked)
            self.run_query()

    @work(group="action")
    async def action_save_view(self) -> None:
        """Save the query as a named view."""
        query = self.bar.value.strip()
        if not query:
            return
        name = await self.push_screen_wait(PromptScreen("Save this query as the view…"))
        if not name:
            return
        try:
            self.views.save(name, query)
        except (ValueError, OSError) as error:
            self.notify(str(error), severity="error")
            return
        self._fill_views()
        self.notify(f"Saved the view {name!r}.")

    def action_refresh(self) -> None:
        """Forget cached answers and run the query again."""
        self.bus.cache.clear()
        clear = getattr(self.catalog, "clear", None)
        if clear:
            clear()
        self.run_query(keep=self.current_key())

    def action_focus_query(self) -> None:
        """Edit the query."""
        self.bar.input.focus()

    def action_focus_views(self) -> None:
        """Go to the views."""
        self.screen.remove_class("-narrow")
        self.query_one("#views").focus()

    def action_help(self) -> None:
        """Show the keys and the query syntax."""
        self.push_screen(HelpScreen())

    def action_activity(self) -> None:
        """Show the activity log."""
        self.push_screen(ActivityScreen(list(self.bus.activity.entries), list(self.plans)))

    def action_cursor(self, step: int) -> None:
        """Move the list cursor."""
        table = self.table
        if self.rows:
            table.move_cursor(row=max(0, min(len(self.rows) - 1, table.cursor_row + step)))

    def action_cursor_edge(self, last: bool) -> None:
        """Jump to the first or last issue."""
        if self.rows:
            self.table.move_cursor(row=len(self.rows) - 1 if last else 0)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Let typing in inputs win over the single-letter keys."""
        focused = self.focused
        typing = focused is not None and focused.__class__.__name__ in ("QueryInput", "Input")
        single = {
            "transition",
            "assign",
            "assign_me",
            "comment",
            "edit_summary",
            "edit_description",
            "labels",
            "priority",
            "watch",
            "new",
            "open",
            "copy",
            "mark",
            "clear_marks",
            "sort",
            "save_view",
            "focus_views",
            "refresh",
            "activity",
            "cursor",
            "cursor_edge",
            "quit",
            "help",
            "focus_query",
        }
        return not (typing and action in single)

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        """Offer every action, and every view, in the command palette."""
        yield from super().get_system_commands(screen)
        for binding in self.BINDINGS:
            if isinstance(binding, Binding) and binding.description:
                action = binding.action
                yield SystemCommand(
                    binding.description,
                    f"Key: {binding.key}",
                    lambda action=action: self.run_action(action),
                )
        for view in self.views.all():
            yield SystemCommand(
                f"View: {view.name}", view.query, lambda q=view.query: self._run_text(q)
            )

    def _run_text(self, query: str) -> None:
        self.bar.value = query
        self.run_query()


def with_order(query: str, order: str) -> str:
    """Return `query` sorted by `order` (smart `sort:` or JQL `ORDER BY`)."""
    if looks_like_jql(query):
        where = re.split(r"(?i)\border\s+by\b", query)[0].strip()
        direction = "DESC" if order.startswith("-") else "ASC"
        name = order.lstrip("-")
        name = {"due": "duedate"}.get(name, name)
        return f"{where} ORDER BY {name} {direction}".strip()
    kept = [t.text for t in terms(query) if not re.match(r"(?i)^-?(sort|order|o):", t.text)]
    return " ".join([*kept, f"sort:{order}"])
