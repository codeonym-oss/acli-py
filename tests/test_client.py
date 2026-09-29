from __future__ import annotations

import pytest

from acli_py.infrastructure.jira.client import (
    API,
    DRY_RUN_ID,
    AuthError,
    JiraClient,
    JiraError,
    NotFoundError,
    normalize_url,
    site_host,
)
from tests import fake_jira


@pytest.fixture
def client(fake, jira):
    _, url = fake
    planned = []
    c = JiraClient(url, fake_jira.EMAIL, fake_jira.TOKEN, on_plan=planned.append)
    c.seen = planned  # type: ignore[attr-defined]
    yield c
    c.close()


def test_urls():
    assert normalize_url("team.atlassian.net/") == "https://team.atlassian.net"
    assert normalize_url("http://localhost:8080") == "http://localhost:8080"
    assert site_host("https://team.atlassian.net/jira") == "team.atlassian.net"


def test_dry_run_reads_but_never_writes(client, jira):
    client.dry_run = True
    assert client.issue("DEMO-1")["key"] == "DEMO-1"
    assert list(client.search("project = DEMO", ["key"]))
    result = client.post(f"{API}/issue", {"fields": {"summary": "x"}})
    client.delete(f"{API}/issue/DEMO-1")
    assert result["key"] == DRY_RUN_ID
    assert [p.method for p in client.planned] == ["POST", "DELETE"]
    assert client.seen == client.planned  # type: ignore[attr-defined]
    assert jira.writes() == []
    assert "DEMO-1" in jira.issues


def test_is_write():
    c = JiraClient("https://x.io", "e", "t")
    try:
        assert not c.is_write("GET", "/anything")
        assert not c.is_write("POST", f"{API}/search/jql")
        assert c.is_write("POST", f"{API}/issue")
        assert c.is_write("PUT", f"{API}/issue/X-1")
    finally:
        c.close()


def test_errors_are_typed(fake, jira):
    _, url = fake
    bad = JiraClient(url, fake_jira.EMAIL, "wrong")
    with pytest.raises(AuthError):
        bad.myself()
    bad.close()
    good = JiraClient(url, fake_jira.EMAIL, fake_jira.TOKEN)
    with pytest.raises(NotFoundError, match="DEMO-999"):
        good.issue("DEMO-999")
    with pytest.raises(JiraError, match="summary"):
        good.post(f"{API}/issue", {"fields": {"project": {"key": "DEMO"}}})
    good.close()


def test_429_is_retried_even_for_post(client, jira):
    client.session.adapters["http://"].max_retries.backoff_factor = 0  # type: ignore[attr-defined]
    jira.fail_next[:] = [429]
    created = client.post(f"{API}/issue", {"fields": {"project": {"key": "DEMO"}, "summary": "s"}})
    assert created["key"] == "DEMO-4"
    assert [e[0] for e in jira.log] == ["POST", "POST"]


def test_502_is_not_retried_for_post(client, jira):
    client.session.adapters["http://"].max_retries.backoff_factor = 0  # type: ignore[attr-defined]
    jira.fail_next[:] = [502]
    with pytest.raises(JiraError, match="502"):
        client.post(f"{API}/issue", {"fields": {"project": {"key": "DEMO"}, "summary": "s"}})
    assert len(jira.log) == 1
    jira.fail_next[:] = [502]
    assert client.myself()["displayName"] == "Alice Martin"


def test_pagination(client, jira):
    for n in range(7):
        jira.add_issue("OPS", f"extra {n}")
    assert len(list(client.paged(f"{API}/project/search", page_size=1))) == 2
    assert len(list(client.search("project = OPS", limit=3))) == 3
    assert len(list(client.search("project = OPS"))) == 8
    assert client.count("project = OPS") == 8
