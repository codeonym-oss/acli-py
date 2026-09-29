"""Drive the TUI with Textual's pilot, against the fake Jira over real HTTP."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC
from typing import TYPE_CHECKING

import pytest
from textual.screen import ModalScreen
from textual.widgets import Input, Markdown, OptionList, TextArea

from acli_py.application.site import Site
from acli_py.bootstrap import build_bus
from acli_py.infrastructure.jira.catalog import JiraCatalog
from acli_py.infrastructure.jira.client import JiraClient
from acli_py.infrastructure.storage import History, Views
from acli_py.presentation.tui.app import IssueBrowser, with_order
from acli_py.presentation.tui.screens import (
    ActivityScreen,
    CreateScreen,
    HelpScreen,
    PickScreen,
    PromptScreen,
    TextScreen,
)
from acli_py.presentation.tui.widgets import ago, issue_markdown, type_cell
from tests import fake_jira

if TYPE_CHECKING:
    from pathlib import Path

SIZE = (160, 44)


def browser(url: str, tmp: Path, *, query: str = "p:DEMO sort:key", dry_run: bool = False):
    client = JiraClient(url, fake_jira.EMAIL, fake_jira.TOKEN, dry_run=dry_run, retries=0)
    return IssueBrowser(
        build_bus(Site(client, url, "", "Alice Martin")),
        JiraCatalog(client),
        query=query,
        default_project="DEMO",
        views=Views(tmp / "views.json"),
        history=History(tmp / "history.json"),
    )


async def settle(pilot, app, seconds: float = 5.0) -> None:
    """Wait until no worker and no message is in flight."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        await pilot.pause(0.05)
        # An action waiting for its dialog is not busy.
        waiting = {"action"} if isinstance(app.screen, ModalScreen) else set()
        busy = app.bus.activity.busy or any(
            w.is_running and w.group not in waiting for w in app.workers
        )
        if not busy:
            await pilot.pause(0.05)
            return
    running = [(w.name, w.group) for w in app.workers if w.is_running]
    raise AssertionError(f"the TUI did not settle: {running}, busy={app.bus.activity.busy}")


async def screen_of(pilot, app, kind, seconds: float = 3.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if isinstance(app.screen, kind):
            await pilot.pause(0.05)
            return app.screen
        await pilot.pause(0.05)
    raise AssertionError(f"{kind.__name__} did not open (on {type(app.screen).__name__})")


async def type_text(pilot, text: str) -> None:
    for char in text:
        await pilot.press({" ": "space", "@": "at", "#": "number_sign", ":": "colon",
                           '"': "quotation_mark", "-": "minus"}.get(char, char))  # fmt: skip


def drive(fake, tmp_path, scenario, **kwargs):
    _, url = fake
    app = browser(url, tmp_path, **kwargs)

    async def main():
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot, app)
            await scenario(pilot, app)

    asyncio.run(main())
    return app


def keys(app) -> list[str]:
    return [row["key"] for row in app.rows]


# ── searching ────────────────────────────────────────────────────────────────


def test_first_query_shows_issues_and_the_detail(site, fake, tmp_path):
    async def scenario(pilot, app):
        assert keys(app) == ["DEMO-1", "DEMO-2", "DEMO-3"]
        assert "project = DEMO ORDER BY key ASC" in str(app.query_one("#jql").render())
        await settle(pilot, app)
        detail = app.query_one("#detail", Markdown)
        assert "Login fails on Safari" in detail.source
        assert "Seen on **Safari 18** too." in detail.source
        await pilot.press("j")
        await settle(pilot, app)
        assert app.current_key() == "DEMO-2"
        assert "Write release notes" in app.query_one("#detail", Markdown).source
        await pilot.press("G")
        assert app.current_key() == "DEMO-3"
        await pilot.press("g")
        assert app.current_key() == "DEMO-1"

    drive(fake, tmp_path, scenario)
    assert site.writes() == []


def test_typing_a_query_with_completion(site, fake, tmp_path):
    async def scenario(pilot, app):
        await pilot.press("slash")
        assert app.bar.input.has_focus
        app.bar.value = ""
        await type_text(pilot, "@me s:")
        await settle(pilot, app)
        assert app.bar.menu_open
        menu = app.bar.menu
        assert menu.option_count == 3  # the statuses
        await pilot.press("down")
        await pilot.press("tab")
        assert app.bar.value == '@me s:"In Progress" '
        await pilot.press("backspace")
        app.bar.value = '@me s:"To Do"'
        await pilot.press("enter")
        await settle(pilot, app)
        assert keys(app) == ["DEMO-1", "OPS-1"]
        assert 'assignee = currentUser() AND status = "To Do"' in str(
            app.query_one("#jql").render()
        )
        assert app.table.has_focus

    app = drive(fake, tmp_path, scenario)
    assert app.history.load()[-1] == '@me s:"To Do"'


def test_bad_queries_say_why_and_keep_the_list(site, fake, tmp_path):
    async def scenario(pilot, app):
        app.bar.value = "updated:soon"
        await pilot.press("slash", "enter")
        await settle(pilot, app)
        assert "can't read 'soon' as a date" in str(app.query_one("#jql").render())
        app.bar.value = "nosuchfield = 3"
        await pilot.press("slash", "enter")
        await settle(pilot, app)
        assert "does not exist" in str(app.query_one("#jql").render())
        assert keys(app) == ["DEMO-1", "DEMO-2", "DEMO-3"]
        app.bar.value = "zzz nothing"
        await pilot.press("slash", "enter")
        await settle(pilot, app)
        assert keys(app) == []
        assert app.query_one("#detail", Markdown).source == "_No issues match._"

    drive(fake, tmp_path, scenario)


def test_escape_closes_the_menu_then_leaves_the_bar(site, fake, tmp_path):
    async def scenario(pilot, app):
        await pilot.press("slash")
        await settle(pilot, app)
        assert app.bar.menu_open
        await pilot.press("escape")
        assert not app.bar.menu_open
        assert app.bar.input.has_focus
        await pilot.press("escape")
        assert app.table.has_focus
        # Single-letter keys type into the bar instead of acting.
        await pilot.press("slash")
        app.bar.value = ""
        await pilot.press("t", "q")
        assert app.bar.value == "tq"
        assert isinstance(app.screen, type(app.screen))
        assert not isinstance(app.screen, PickScreen)

    drive(fake, tmp_path, scenario)


def test_empty_query_uses_the_default_project(site, fake, tmp_path):
    async def scenario(pilot, app):
        assert "project = DEMO ORDER BY updated DESC" in str(app.query_one("#jql").render())

    drive(fake, tmp_path, scenario, query="  ")


def test_views_sidebar_runs_views_and_filters(site, fake, tmp_path):
    async def scenario(pilot, app):
        await settle(pilot, app)
        menu = app.query_one("#views", OptionList)
        labels = [str(menu.get_option_at_index(i).prompt) for i in range(menu.option_count)]
        assert "⚑ My open work" in labels  # a favourite filter
        assert any("p:DEMO sort:key" in label for label in labels)  # history
        await pilot.press("v")
        assert menu.has_focus
        menu.highlighted = labels.index("  Current sprint")
        await pilot.press("enter")
        await settle(pilot, app)
        assert app.bar.value.startswith("is:sprint")
        assert app.table.has_focus

    drive(fake, tmp_path, scenario)


def test_pages_load_as_you_scroll(site, fake, tmp_path):
    for n in range(60):
        site.add_issue("DEMO", f"Filler {n}", "Task")

    async def scenario(pilot, app):
        assert len(app.rows) == 50
        await pilot.press("G")
        await settle(pilot, app)
        assert len(app.rows) == 63
        assert app.next_token is None
        assert "63" in str(app.query_one("#status").render())

    drive(fake, tmp_path, scenario)


# ── changing issues ──────────────────────────────────────────────────────────


def test_transition_assign_and_comment(site, fake, tmp_path):
    async def scenario(pilot, app):
        await pilot.press("t")
        picker = await screen_of(pilot, app, PickScreen)
        await type_text(pilot, "fin")
        assert [c.value for c in picker.shown] == ["Done"]
        await pilot.press("enter")
        await settle(pilot, app)
        row = app.rows[0]
        assert row["fields"]["status"]["name"] == "Done"

        await pilot.press("a")
        picker = await screen_of(pilot, app, PickScreen)
        await type_text(pilot, "carol")
        await settle(pilot, app)
        assert [c.label for c in picker.shown] == ["Carol Jensen"]
        await pilot.press("enter")
        await settle(pilot, app)

        await pilot.press("c")
        editor = await screen_of(pilot, app, TextScreen)
        await pilot.press("ctrl+s")  # empty: refused
        assert isinstance(app.screen, TextScreen)
        editor.query_one(TextArea).text = "Fixed in **2.4**"
        await pilot.press("ctrl+s")
        await settle(pilot, app)

    drive(fake, tmp_path, scenario)
    issue = site.issues["DEMO-1"]
    assert issue["fields"]["status"]["name"] == "Done"
    assert issue["fields"]["assignee"]["displayName"] == "Carol Jensen"
    assert issue["comments"][-1]["body"]["content"][0]["content"][1]["text"] == "2.4"


def test_bulk_actions_on_marked_issues(site, fake, tmp_path):
    async def scenario(pilot, app):
        await pilot.press("space", "space")  # marks DEMO-1 and DEMO-2
        assert app.marked == ["DEMO-1", "DEMO-2"]
        assert "2 marked" in str(app.query_one("#status").render())
        await pilot.press("A")
        await settle(pilot, app)
        await pilot.press("l")
        prompt = await screen_of(pilot, app, PromptScreen)
        prompt.query_one(Input).value = "triage -web"
        await pilot.press("enter")
        await settle(pilot, app)
        await pilot.press("p")
        picker = await screen_of(pilot, app, PickScreen)
        await type_text(pilot, "high")
        assert [c.value for c in picker.shown] == ["High"]
        await pilot.press("enter")
        await settle(pilot, app)
        await pilot.press("t")
        picker = await screen_of(pilot, app, PickScreen)
        assert {c.value for c in picker.shown} == {"In Progress", "Done"}
        await pilot.press("escape")
        await pilot.press("x")
        assert app.marked == []

    drive(fake, tmp_path, scenario)
    for key in ("DEMO-1", "DEMO-2"):
        fields = site.issues[key]["fields"]
        assert fields["assignee"]["displayName"] == "Alice Martin"
        assert "triage" in fields["labels"]
        assert "web" not in fields["labels"]
        assert fields["priority"]["name"] == "High"
    assert site.issues["DEMO-3"]["fields"]["assignee"] is None


def test_edit_summary_description_and_watch(site, fake, tmp_path):
    async def scenario(pilot, app):
        await pilot.press("e")
        prompt = await screen_of(pilot, app, PromptScreen)
        assert prompt.query_one(Input).value == "Login fails on Safari"
        prompt.query_one(Input).value = "Login fails on Safari 18"
        await pilot.press("enter")
        await settle(pilot, app)
        assert app.rows[0]["fields"]["summary"] == "Login fails on Safari 18"

        await pilot.press("d")
        editor = await screen_of(pilot, app, TextScreen)
        assert "Steps to reproduce." in editor.query_one(TextArea).text
        editor.query_one(TextArea).text = "New *steps*."
        await pilot.press("ctrl+s")
        await settle(pilot, app)

        await pilot.press("w")
        await settle(pilot, app)

    drive(fake, tmp_path, scenario)
    issue = site.issues["DEMO-1"]
    assert issue["fields"]["summary"] == "Login fails on Safari 18"
    assert issue["fields"]["description"]["content"][0]["content"][1]["text"] == "steps"
    assert any(path.endswith("/watchers") for _, path, _ in site.writes())


def test_new_issue(site, fake, tmp_path):
    async def scenario(pilot, app):
        await pilot.press("n")
        form = await screen_of(pilot, app, CreateScreen)
        await settle(pilot, app)
        await pilot.press("ctrl+s")  # no summary yet: refused
        assert isinstance(app.screen, CreateScreen)
        form.query_one("#summary", Input).value = "Add dark mode"
        form.query_one("#labels", Input).value = "ui, theme"
        form.query_one("#description", TextArea).text = "Please."
        await pilot.press("ctrl+s")
        await settle(pilot, app)
        assert "Add dark mode" in [r["fields"]["summary"] for r in app.rows]

    drive(fake, tmp_path, scenario)
    created = next(i for i in site.issues.values() if i["fields"]["summary"] == "Add dark mode")
    assert created["key"].startswith("DEMO-")
    assert created["fields"]["labels"] == ["ui", "theme"]
    assert created["fields"]["assignee"]["displayName"] == "Alice Martin"


def test_dry_run_sends_nothing_and_logs_the_plans(site, fake, tmp_path):
    async def scenario(pilot, app):
        assert "DRY RUN" in str(app.query_one("#top").render())
        await pilot.press("A")
        await settle(pilot, app)
        await pilot.press("c")
        editor = await screen_of(pilot, app, TextScreen)
        editor.query_one(TextArea).text = "hello"
        await pilot.press("ctrl+s")
        await settle(pilot, app)
        assert len(app.plans) == 2
        await pilot.press("L")
        log = await screen_of(pilot, app, ActivityScreen)
        assert log.plans[0].method == "PUT"
        await pilot.press("escape")

    drive(fake, tmp_path, scenario, dry_run=True)
    assert site.writes() == []


def test_failures_are_shown_not_raised(site, fake, tmp_path):
    async def scenario(pilot, app):
        site.fail_next.append(400)  # who am I? fails: said, not raised
        await pilot.press("A")
        await settle(pilot, app)
        assert site.writes() == []
        await pilot.press("A")  # now it works, but the assignment fails
        await settle(pilot, app)
        site.fail_next.append(400)
        await pilot.press("A")
        await settle(pilot, app)
        assert app.bus.activity.entries[-1].error

    drive(fake, tmp_path, scenario)


# ── the rest of the keys ─────────────────────────────────────────────────────


def test_sort_save_view_help_copy_and_refresh(site, fake, tmp_path, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr("webbrowser.open", opened.append)

    async def scenario(pilot, app):
        await pilot.press("S")
        await screen_of(pilot, app, PickScreen)
        await type_text(pilot, "newest")
        await pilot.press("enter")
        await settle(pilot, app)
        assert app.bar.value == "p:DEMO sort:-created"

        await pilot.press("s")
        prompt = await screen_of(pilot, app, PromptScreen)
        prompt.query_one(Input).value = "Demo newest"
        await pilot.press("enter")
        await settle(pilot, app)
        assert app.views.find("Demo newest").query == "p:DEMO sort:-created"

        await pilot.press("question_mark")
        await screen_of(pilot, app, HelpScreen)
        await pilot.press("escape")

        await pilot.press("y")
        await pilot.press("o")
        await pilot.press("r")
        await settle(pilot, app)
        assert len(app.rows) == 3

    drive(fake, tmp_path, scenario)
    assert len(opened) == 1
    assert opened[0].split("/browse/")[1].startswith("DEMO-")


def test_palette_lists_actions_and_views(site, fake, tmp_path):
    async def scenario(pilot, app):
        titles = [c.title for c in app.get_system_commands(app.screen)]
        assert "Transition" in titles
        assert "View: Overdue" in titles
        command = next(c for c in app.get_system_commands(app.screen) if c.title == "View: Overdue")
        command.callback()
        await settle(pilot, app)
        assert app.bar.value.startswith("is:overdue")

    drive(fake, tmp_path, scenario)


def test_narrow_terminals_hide_panes(site, fake, tmp_path):
    async def scenario(pilot, app):
        await pilot.resize_terminal(100, 40)
        await settle(pilot, app)
        assert app.screen.has_class("-narrow")
        await pilot.resize_terminal(80, 40)
        await settle(pilot, app)
        assert app.screen.has_class("-tiny")

    drive(fake, tmp_path, scenario)


# ── helpers ──────────────────────────────────────────────────────────────────


def test_with_order():
    assert with_order("@me sort:key", "-updated") == "@me sort:-updated"
    assert (
        with_order("project = X ORDER BY key", "-priority") == "project = X ORDER BY priority DESC"
    )
    assert with_order("status = Done", "due") == "status = Done ORDER BY duedate ASC"


@pytest.mark.parametrize(
    ("stamp", "shown"),
    [
        ("2026-09-29T11:55:00.000+0000", "5m"),
        ("2026-09-29T09:00:00.000+0000", "3h"),
        ("2026-09-26T12:00:00.000+0000", "3d"),
        ("2026-08-01T12:00:00.000+0000", "8w"),
        ("2025-01-01T12:00:00.000+0000", "2025-01-01"),
        ("2026-09-29T11:59:59.000+0000", "now"),
        ("2026-09-29", "2026-09-29"),
        (None, ""),
    ],
)
def test_ago(stamp, shown):
    from datetime import datetime

    now = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    assert ago(stamp, now) == shown


def test_type_badges():
    assert type_cell({"name": "Bug"}).plain == "B"
    assert type_cell({"name": "Sub-task", "subtask": True}).plain == "↳"
    assert type_cell({"name": "Idea"}).plain == "I"
    assert type_cell(None).plain == ""


def test_issue_markdown_shows_everything_there_is():
    issue = {
        "key": "DEMO-9",
        "fields": {
            "summary": "S",
            "parent": {"key": "DEMO-1", "fields": {"summary": "Epic"}},
            "subtasks": [
                {"key": "DEMO-10", "fields": {"summary": "Sub", "status": {"name": "Done"}}}
            ],
            "issuelinks": [
                {
                    "type": {"inward": "is blocked by"},
                    "inwardIssue": {"key": "DEMO-2", "fields": {"summary": "B"}},
                }
            ],
            "comment": {
                "comments": [{"author": {"displayName": "Bob"}, "body": f"c{n}"} for n in range(7)]
            },
        },
    }
    text = issue_markdown(issue, "https://x/browse/DEMO-9")
    assert "**Parent:** DEMO-1 Epic" in text
    assert "- **DEMO-10** [Done] Sub" in text
    assert "- is blocked by **DEMO-2** B" in text
    assert "_2 older not shown._" in text
    assert "_No description._" in text
