"""Regenerate the TUI screenshots in docs/_static from a fake Jira site.

Run from the repository root: `uv run python scripts/tui_screenshots.py`.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acli_py.bootstrap import build_bus, build_catalog
from acli_py.infrastructure.jira.client import JiraClient
from acli_py.infrastructure.jira.site import Site
from acli_py.infrastructure.storage import History, Views
from acli_py.presentation.tui.app import IssueBrowser
from tests import fake_jira

OUT = Path(__file__).resolve().parent.parent / "docs" / "_static"


async def shoot(app: IssueBrowser) -> None:
    """Save the browser, then the query bar completing a status."""
    async with app.run_test(size=(150, 36)) as pilot:
        await pilot.pause(1.5)
        app.save_screenshot(str(OUT / "tui.svg"))
        await pilot.press("slash")
        app.bar.value = "@me s:"
        await pilot.pause(1.0)
        app.save_screenshot(str(OUT / "tui-complete.svg"))


def main() -> None:
    """Start the fake site, fill it with a few issues and take the screenshots."""
    server, jira, url = fake_jira.start()
    try:
        jira.add_issue(
            "DEMO", "Dark mode for the settings page", "Story",
            assignee=fake_jira.ALICE, labels=["ui"], status="3",
        )  # fmt: skip
        jira.add_issue(
            "DEMO", "Crash when exporting large CSV files", "Bug",
            assignee=fake_jira.BOB, labels=["export"],
        )  # fmt: skip
        jira.add_issue("DEMO", "Epic: onboarding revamp", "Epic")
        state = Path(tempfile.mkdtemp())
        History(state / "history.json").add("@me is:open sort:-priority")
        client = JiraClient(url, fake_jira.EMAIL, fake_jira.TOKEN)
        site = Site(client, "https://demo.atlassian.net", "", "Alice Martin")
        app = IssueBrowser(
            build_bus(site),
            build_catalog(site),
            query="p:DEMO sort:key",
            views=Views(state / "views.json"),
            history=History(state / "history.json"),
        )
        asyncio.run(shoot(app))
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
