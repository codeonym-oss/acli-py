from __future__ import annotations

import json
import os
import stat

from acli_py.infrastructure.config import Config, config_dir
from tests import fake_jira
from tests.conftest import run_cli


def login(url: str, email: str = fake_jira.EMAIL, token: str = fake_jira.TOKEN):
    return run_cli("auth", "login", "--site", url, "--email", email, "--token", token)


def test_login_stores_the_token_owner_only_and_never_in_the_config(fake, jira):
    _, url = fake
    result, out = login(url)
    assert result.exit_code == 0, out
    assert "Alice Martin" in out
    tokens = config_dir() / "credentials.json"
    assert fake_jira.TOKEN in tokens.read_text()
    assert fake_jira.TOKEN not in (config_dir() / "config.json").read_text()
    if os.name == "posix":
        assert stat.S_IMODE(tokens.stat().st_mode) == 0o600
        assert stat.S_IMODE(config_dir().stat().st_mode) == 0o700
    account = Config.load().account
    assert account is not None
    assert account.account_id == fake_jira.ALICE["accountId"]
    assert account.time_zone == "Europe/Paris"


def test_login_rejects_a_bad_token_and_saves_nothing(fake, jira):
    _, url = fake
    result, out = login(url, token="nope")
    assert result.exit_code == 1
    assert "rejected the credentials" in out
    assert not (config_dir() / "config.json").exists()


def test_token_from_stdin(fake, jira):
    _, url = fake
    result, out = run_cli(
        "auth", "login", "-s", url, "-e", fake_jira.EMAIL, "--token-stdin",
        input=fake_jira.TOKEN + "\n",
    )  # fmt: skip
    assert result.exit_code == 0, out


def test_status_switch_and_logout_with_two_accounts(fake, jira):
    _, url = fake
    login(url)
    other = url.replace("127.0.0.1", "localhost")
    login(other)
    config = Config.load()
    assert len(config.accounts) == 2
    assert config.active
    assert config.active.endswith("localhost:" + url.rsplit(":", 1)[1])

    result, out = run_cli("auth", "status", "--json")
    rows = json.loads(out)
    assert [r["active"] for r in rows] == [False, True]

    result, out = run_cli("auth", "switch", "--site", url)
    assert result.exit_code == 0, out
    assert Config.load().active == f"{fake_jira.EMAIL}@127.0.0.1:{url.rsplit(':', 1)[1]}"

    result, out = run_cli("auth", "switch")
    assert result.exit_code == 1
    assert "Several accounts match" in out

    result, out = run_cli("auth", "status", "--check")
    assert result.exit_code == 0, out
    assert "is valid" in out

    result, out = run_cli("auth", "logout")
    assert result.exit_code == 0, out
    assert "Active account is now" in out
    result, out = run_cli("auth", "logout", "--all")
    assert result.exit_code == 0, out
    assert Config.load().accounts == {}
    assert not (config_dir() / "credentials.json").exists()
    result, out = run_cli("auth", "status")
    assert result.exit_code == 1


def test_commands_need_a_login(jira):
    result, out = run_cli("issue", "view", "DEMO-1")
    assert result.exit_code == 1
    assert "Not logged in" in out


def test_environment_account_for_ci(fake, jira, monkeypatch):
    _, url = fake
    monkeypatch.setenv("ACLI_PY_SITE", url)
    monkeypatch.setenv("ACLI_PY_EMAIL", fake_jira.EMAIL)
    monkeypatch.setenv("ACLI_PY_API_TOKEN", fake_jira.TOKEN)
    result, out = run_cli("issue", "view", "DEMO-1")
    assert result.exit_code == 0, out
    assert "Login fails on Safari" in out


def test_account_option_picks_a_saved_account(fake, jira):
    _, url = fake
    login(url)
    result, out = run_cli("--account", "nobody@nowhere", "issue", "view", "DEMO-1")
    assert result.exit_code == 1
    assert "matches 0 saved accounts" in out
    result, out = run_cli("--account", fake_jira.EMAIL, "issue", "view", "DEMO-1")
    assert result.exit_code == 0, out


def test_config_defaults(site):
    result, out = run_cli("config", "set", "project", "demo")
    assert result.exit_code == 0, out
    assert Config.load().defaults == {"project": "DEMO"}
    result, out = run_cli("config", "set", "colour", "red")
    assert result.exit_code == 1
    assert "Unknown setting" in out
    result, out = run_cli("config", "show", "--json")
    assert json.loads(out)["defaults"] == {"project": "DEMO"}
    result, out = run_cli("config", "show")
    assert "issue-type" in out
    result, out = run_cli("config", "unset", "project")
    assert result.exit_code == 0
    result, out = run_cli("config", "unset", "project")
    assert "was not set" in out
    result, out = run_cli("config", "path")
    assert "config.json" in out


def test_version():
    result, out = run_cli("--version")
    assert result.exit_code == 0
    assert out.startswith("acli-py ")
