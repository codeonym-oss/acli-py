from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from acli_py.application.bus import Bus
    from acli_py.application.events.issue_changed.event import IssueChanged

from acli_py.application.behaviors import describe
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
from acli_py.application.site import Site
from acli_py.bootstrap import build_bus
from acli_py.infrastructure.jira.client import JiraClient, NotFoundError
from acli_py.infrastructure.storage import BUILTIN_VIEWS, History, Views
from tests import fake_jira


def make_bus(url: str, *, dry_run: bool = False) -> Bus:
    client = JiraClient(url, fake_jira.EMAIL, fake_jira.TOKEN, dry_run=dry_run, retries=0)
    return build_bus(Site(client, url), assume_yes=True)


def run(coro):
    return asyncio.run(coro)


def test_queries_read_and_are_cached(site, fake):
    _, url = fake
    bus = make_bus(url)

    async def scenario():
        page = await bus.send(SearchIssues("project = DEMO ORDER BY key", size=2))
        assert [i["key"] for i in page.issues] == ["DEMO-1", "DEMO-2"]
        more = await bus.send(SearchIssues(page.jql, token=page.next_token, size=2))
        assert [i["key"] for i in more.issues] == ["DEMO-3"]
        assert more.next_token is None
        assert await bus.send(CountIssues("project = DEMO")) == 3
        view = await bus.send(GetIssue("DEMO-1"))
        assert view.issue.summary == "Login fails on Safari"
        assert [t["name"] for t in await bus.send(GetTransitions("DEMO-1"))] == [
            "Start work",
            "Finish",
        ]
        assert [u["displayName"] for u in await bus.send(FindAssignees("DEMO-1", "bob"))] == [
            "Bob Jensen"
        ]
        assert await bus.send(ValidateJql("project = DEMO")) == []
        assert await bus.send(ValidateJql("nosuchfield = 1")) != []
        assert [f["name"] for f in await bus.send(ListFilters())] == ["My open work"]
        assert [p["name"] for p in await bus.send(ListPriorities())] == ["High", "Medium", "Low"]
        assert {p["key"] for p in await bus.send(ListProjects())} == {"DEMO", "OPS"}
        types = [t["name"] for t in await bus.send(ListIssueTypes("DEMO"))]
        assert "Subtask" not in types
        assert "Bug" in types
        before = len(site.log)
        await bus.send(GetIssue("DEMO-1"))
        assert len(site.log) == before  # answered from the cache

    run(scenario())
    assert site.writes() == []
    names = [entry.name for entry in bus.activity.entries]
    assert "SearchIssues" in names
    assert bus.activity.busy == 0


def test_commands_change_jira_empty_the_cache_and_announce(site, fake):
    _, url = fake
    bus = make_bus(url)
    heard: list[IssueChanged] = []
    bus.listeners.append(heard.append)

    async def scenario():
        await bus.send(GetIssue("DEMO-2"))
        await bus.send(TransitionIssue("DEMO-2", "In Progress", comment="Starting"))
        assert (await bus.send(GetIssue("DEMO-2"))).issue.status.name == "In Progress"
        await bus.send(AssignIssue("DEMO-2", fake_jira.CAROL["accountId"], "Carol"))
        await bus.send(CommentOnIssue("DEMO-2", "Looks **good**"))
        await bus.send(
            EditIssue(
                "DEMO-2",
                {"summary": "Write the notes"},
                {"labels": [{"add": "docs2"}, {"remove": "docs"}]},
            )
        )
        await bus.send(EditIssue("DEMO-2"))  # nothing to change: no request
        await bus.send(WatchIssue("DEMO-2", fake_jira.ALICE["accountId"], True))
        await bus.send(WatchIssue("DEMO-2", fake_jira.ALICE["accountId"], False))
        return await bus.send(
            CreateIssue("DEMO", "Task", " New thing ", "Some *text*", True, ("x",))
        )

    key = run(scenario())
    issue = site.issues["DEMO-2"]
    assert issue["fields"]["assignee"]["displayName"] == "Carol Jensen"
    assert issue["fields"]["summary"] == "Write the notes"
    assert issue["fields"]["labels"] == ["docs2"]
    assert issue["comments"][-1]["body"]["content"][0]["content"][1]["text"] == "good"
    created = site.issues[key]
    assert created["fields"]["summary"] == "New thing"
    assert created["fields"]["assignee"]["accountId"] == fake_jira.ALICE["accountId"]
    assert [h.what for h in heard] == [
        "TransitionIssue", "AssignIssue", "CommentOnIssue", "EditIssue", "EditIssue",
        "WatchIssue", "WatchIssue", "CreateIssue",
    ]  # fmt: skip
    assert heard[-1].key == key
    assert not any(h.dry_run for h in heard)


def test_dry_run_commands_plan_and_say_so(site, fake):
    _, url = fake
    bus = make_bus(url, dry_run=True)
    heard: list[IssueChanged] = []

    async def listener(change):
        heard.append(change)

    bus.listeners.append(listener)
    run(bus.send(AssignIssue("DEMO-1", None)))
    assert site.writes() == []
    assert len(bus.site.client.planned) == 1
    assert heard[0].dry_run


def test_failures_reach_the_caller_and_the_log(site, fake):
    _, url = fake
    bus = make_bus(url)
    with pytest.raises(NotFoundError):
        run(bus.send(GetIssue("NOPE-1")))
    assert bus.activity.entries[-1].error


def test_site_asks_who_i_am_once(site, fake):
    _, url = fake
    bus = make_bus(url)
    assert bus.site.me == fake_jira.ALICE["accountId"]
    calls = len(site.log)
    assert bus.site.me == fake_jira.ALICE["accountId"]
    assert len(site.log) == calls
    assert bus.site.browse("DEMO-1").endswith("/browse/DEMO-1")


def test_describe_keeps_the_log_short():
    text = describe(CommentOnIssue("DEMO-1", "x" * 100))
    assert text.startswith("key=DEMO-1 body=")
    assert text.endswith("…")


def test_views(tmp_path):
    views = Views(tmp_path / "views.json")
    assert views.all() == list(BUILTIN_VIEWS)
    views.save("Mine", "@me")
    views.save("mine", "@me is:open")  # replaces, whatever the case
    assert [(v.name, v.query) for v in views.saved()] == [("mine", "@me is:open")]
    mine, sprint = views.find("MINE"), views.find("Current sprint")
    assert mine is not None
    assert mine.query == "@me is:open"
    assert sprint is not None
    assert sprint.builtin
    with pytest.raises(ValueError, match="built-in"):
        views.save("Overdue", "x")
    with pytest.raises(ValueError, match="needs a name"):
        views.save(" ", "x")
    assert views.delete("Mine")
    assert not views.delete("Mine")
    (tmp_path / "views.json").write_text("not json")
    assert views.saved() == []


def test_history(tmp_path):
    history = History(tmp_path / "h.json", size=3)
    for query in ("a", "b", "a", "c", "d", " "):
        history.add(query)
    assert history.load() == ["a", "c", "d"]
    (tmp_path / "h.json").write_text("{}")
    assert history.load() == []
