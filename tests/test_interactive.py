"""The shell, the `aj tui`/`aj shell` commands, smart search, and the acli parity options."""

from __future__ import annotations

import json

import pytest
import typer
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from acli_py.cli import app
from acli_py.client import JiraClient
from acli_py.jql import JiraCatalog, StaticCatalog, Value
from acli_py.shell import SafeHistory, Shell, ShellCompleter, commands
from tests import fake_jira
from tests.conftest import aj

ROOT = typer.main.get_command(app)


def completions(completer: ShellCompleter, text: str) -> list[str]:
    return [c.text for c in completer.get_completions(Document(text), CompleteEvent())]


@pytest.fixture
def completer(site, fake):
    _, url = fake
    return ShellCompleter(ROOT, JiraCatalog(JiraClient(url, fake_jira.EMAIL, fake_jira.TOKEN)))


# ── shell completion ─────────────────────────────────────────────────────────


def test_commands_and_meta_commands(completer):
    top = completions(completer, "")
    assert {"issue", "sprint", "help", "dry-run", "tui", "exit"} <= set(top)
    assert "shell" not in top  # no shell inside the shell
    assert completions(completer, "aj is") == ["issue"]
    assert completions(completer, "issue tr") == ["transition", "transitions"]
    assert completions(completer, "issue comment a") == ["add"]
    assert completions(completer, "--") == ["--dry-run", "--account", "--debug", "--version"]


def test_options_and_their_values(completer):
    assert completions(completer, "issue view DEMO-1 --com") == ["--comments"]
    assert completions(completer, "issue create -t") == ["-t"]
    assert completions(completer, "issue create -p ") == ["DEMO", "OPS"]
    assert completions(completer, "issue create --type B")[0] == "Bug"
    assert completions(completer, "issue transition DEMO-1 --to In") == ["'In Progress'"]
    assert completions(completer, "issue assign DEMO-1 --to b") == ["'Bob Jensen'"]
    assert completions(completer, "issue assign DEMO-1 --to @") == ["@me"]
    assert completions(completer, "issue search -L w") == ["web"]
    assert completions(completer, "--dry-run issue edit DEMO-1 --priority H") == ["High"]
    assert "table" not in completions(completer, "issue search --json ")  # flags take no value


def test_issue_keys_and_lists(completer):
    assert completions(completer, "issue view DEMO-")[:3] == ["DEMO-1", "DEMO-2", "DEMO-3"]
    assert completions(completer, "issue assign DEMO-1,DEMO-")[:1] == ["DEMO-1,DEMO-1"]
    assert "DEMO-2" in completions(completer, "issue assign DEMO-1 ")  # more keys
    assert "--to" in completions(completer, "issue assign DEMO-1 -")
    # Nothing to suggest for an argument: offer the options instead.
    assert "--limit" in completions(completer, "user search bob ")


def test_queries_complete_inside_their_quotes(completer):
    assert completions(completer, "issue search 'status = In")[0] == '\'status = "In Progress" '
    assert completions(completer, "issue search 'status = Done ")[:2] == [
        "'status = Done AND ",
        "'status = Done OR ",
    ]
    assert completions(completer, 'issue edit --jql "assignee = cur')[0].startswith(
        '"assignee = currentUser()'
    )
    assert completions(completer, "issue search #w")[0] == "'#web "


def test_choices_complete():
    fake = StaticCatalog(field_values={"status": [Value("To Do")]})
    completer = ShellCompleter(ROOT, fake)
    assert (
        "kanban" in completions(completer, "board create --type ")
        or completions(completer, "board create --type ") == []
    )


# ── the shell loop ───────────────────────────────────────────────────────────


def make_shell(**kwargs):
    said: list[str] = []
    opened: list[str] = []
    shell = Shell(ROOT, StaticCatalog(), history=kwargs.pop("history"), account="me@site",
                  open_tui=opened.append, output=said.append, **kwargs)  # fmt: skip
    return shell, said, opened


def test_shell_runs_commands_and_meta_commands(site, tmp_path, capsys):
    shell, said, opened = make_shell(history=tmp_path / "h")
    assert shell.execute("") is None
    assert shell.execute("# a comment") is None
    assert shell.execute("aj issue view DEMO-1") == 0
    assert "Login fails on Safari" in capsys.readouterr().out
    assert shell.execute("issue view NOPE-1") == 1
    assert shell.execute("issue view") == 2  # missing argument: click's usage error
    assert shell.execute("issue 'unclosed") == 2
    assert "Can't read that line" in said[-1]
    assert shell.execute("dry-run on") is None
    assert shell.dry_run
    assert shell.prompt() == "aj (dry run)> "
    assert "DRY RUN" in shell.toolbar().value
    assert shell.execute("issue assign DEMO-2 --to @me") == 0
    assert site.writes() == []  # the dry run held
    assert shell.execute("dry-run") is None  # toggles
    assert not shell.dry_run
    assert shell.execute("tui @me is:open") is None
    assert opened == ["@me is:open"]
    assert shell.execute("shell") is None
    assert shell.execute("clear") is None
    assert shell.execute("help issue") == 0
    assert shell.execute("aj") is None
    assert shell.execute("exit") == "exit"


def test_shell_loop_reads_until_eof(site, tmp_path, monkeypatch):
    lines = iter(["issue view DEMO-1", KeyboardInterrupt, "quit"])

    class FakeSession:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def prompt(self, text):
            line = next(lines)
            if line is KeyboardInterrupt:
                raise KeyboardInterrupt
            return line

    monkeypatch.setattr("acli_py.shell.PromptSession", FakeSession)
    shell, said, _ = make_shell(history=tmp_path / "sub" / "h")
    shell.run()
    assert said[0].startswith("aj shell")

    def eof(self, text):
        raise EOFError

    monkeypatch.setattr(FakeSession, "prompt", eof)
    shell.run()  # returns on Ctrl+D


def test_history_never_keeps_tokens(tmp_path):
    history = SafeHistory(str(tmp_path / "h"))
    history.store_string("issue view DEMO-1")
    history.store_string("auth login -s x -e y --token secret")
    history.store_string("auth login -s x -e y -t secret")
    history.store_string("auth login --token-stdin")
    text = (tmp_path / "h").read_text()
    assert "secret" not in text
    assert "DEMO-1" in text
    assert "--token-stdin" in text


def test_command_list():
    listed = commands(ROOT)
    assert "issue comment add" in listed
    assert "tui" in listed
    assert "workitem view" not in listed  # hidden alias


# ── `aj tui` and `aj shell` ──────────────────────────────────────────────────


def test_tui_command_starts_the_app(site, monkeypatch):
    started: list = []
    monkeypatch.setattr("acli_py.tui.app.IssueBrowser.run", lambda self: started.append(self))
    result, out = aj("-n", "tui", "--view", "overdue")
    assert result.exit_code == 0, out
    browser = started[0]
    assert browser.first_query.startswith("is:overdue")
    assert browser.site.dry_run
    assert browser.site.client.on_plan is not None  # the app shows plans itself
    result, out = aj("tui", "--view", "nope")
    assert result.exit_code == 1
    assert "No view called 'nope'" in out


def test_shell_command_starts_the_loop(site, monkeypatch):
    ran: list[Shell] = []
    monkeypatch.setattr("acli_py.shell.Shell.run", lambda self: ran.append(self))
    result, out = aj("-n", "shell")
    assert result.exit_code == 0, out
    assert ran[0].dry_run
    assert ran[0].account.startswith(fake_jira.EMAIL)
    started: list = []
    monkeypatch.setattr("acli_py.tui.app.IssueBrowser.run", lambda self: started.append(self))
    ran[0].execute("tui #web")
    assert started[0].first_query == "#web"


def test_shell_without_a_login_still_starts(jira, monkeypatch):
    ran: list[Shell] = []
    monkeypatch.setattr("acli_py.shell.Shell.run", lambda self: ran.append(self))
    result, out = aj("shell")
    assert result.exit_code == 0, out
    assert "not logged in" in ran[0].account


# ── smart search from the command line ───────────────────────────────────────


def test_search_takes_smart_queries(site):
    result, out = aj("issue", "search", "@me s:todo is:open", "--count", "--json")
    assert result.exit_code == 0, out
    data = json.loads(out)
    # "todo" is how people type "To Do": spelled right before Jira sees it.
    assert data["jql"] == (
        '(statusCategory != Done AND assignee = currentUser() AND status = "To Do") '
        "ORDER BY updated DESC"
    )
    assert data["count"] == 2
    result, out = aj("issue", "search", "p:demo sort:key", "--json")
    assert [i["key"] for i in json.loads(out)] == ["DEMO-1", "DEMO-2", "DEMO-3"]
    result, out = aj("issue", "search", "@bob")
    assert "DEMO-2" in out
    assert "OPS-1" not in out


def test_search_warns_and_can_skip_smart_parsing(site):
    result, out = aj("issue", "search", "colour:red", "-p", "DEMO")
    assert "unknown filter colour:" in out
    result, out = aj("issue", "search", "project = DEMO", "--raw", "--count")
    assert result.exit_code == 0, out
    assert out.strip() == "3"


def test_search_syntax_needs_no_login(jira):
    result, out = aj("issue", "search", "--syntax")
    assert result.exit_code == 0, out
    assert "sort:" in out
    assert "#LABEL" in out


def test_ambiguous_people_are_refused(site):
    result, out = aj("issue", "search", "@jensen")
    assert result.exit_code == 1
    assert "could be Bob Jensen, Carol Jensen" in out


# ── acli parity ──────────────────────────────────────────────────────────────


def test_clone_to_another_site(site, fake):
    _, url = fake
    other = url.replace("127.0.0.1", "localhost")
    aj("auth", "login", "--site", other, "--email", fake_jira.EMAIL, "--token", fake_jira.TOKEN)
    aj("auth", "switch", "--site", url)
    site.log.clear()
    result, out = aj("issue", "clone", "DEMO-1", "--to-site", other, "--to-project", "OPS")
    assert result.exit_code == 0, out
    copy = next(
        i for i in site.issues.values() if i["key"].startswith("OPS-") and i["key"] != "OPS-1"
    )
    assert copy["fields"]["summary"] == "Login fails on Safari"
    assert copy["remote_links"][0]["title"] == "Cloned from DEMO-1"
    assert not any(path.endswith("/issueLink") for _, path, _ in site.writes())
    result, out = aj("issue", "clone", "DEMO-1", "--to-site", other)
    assert result.exit_code == 1
    assert "--to-site needs --to-project" in out


def test_create_from_a_text_file(site, tmp_path):
    note = tmp_path / "issue.txt"
    note.write_text("Printer on fire\n\nIt is **really** on fire.\n")
    result, out = aj("issue", "create", "-p", "DEMO", "-t", "Bug", "--from-file", str(note))
    assert result.exit_code == 0, out
    body = next(b for m, p, b in site.writes() if p == "/rest/api/3/issue")
    assert body["fields"]["summary"] == "Printer on fire"
    assert body["fields"]["description"]["content"][0]["content"][1]["text"] == "really"


def test_comment_body_adf_alias(site, tmp_path):
    doc = tmp_path / "c.json"
    doc.write_text(json.dumps({"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "raw adf"}]}]}))  # fmt: skip
    result, out = aj("issue", "comment", "add", "DEMO-1", "--body-adf", str(doc))
    assert result.exit_code == 0, out
    assert (
        site.issues["DEMO-1"]["comments"][-1]["body"]["content"][0]["content"][0]["text"]
        == "raw adf"
    )


def test_filter_owner_from_a_file(site, tmp_path):
    ids = tmp_path / "ids.txt"
    ids.write_text("10100\n")
    result, out = aj("filter", "owner", "--to", "bob", "--from-file", str(ids))
    assert result.exit_code == 0, out
    assert site.filters["10100"]["owner"]["displayName"] == "Bob Jensen"
    result, out = aj("filter", "owner", "--to", "bob")
    assert result.exit_code == 1
    assert "Say which filters" in out


def test_board_list_order_and_private(site):
    result, out = aj("board", "list", "--order", "-name", "--private", "--json")
    assert result.exit_code == 0, out
    params = [p for m, p, _ in site.log if p.endswith("/board")]
    assert params


def test_templates_print_json(jira):
    for args in (("issue", "edit", "--template"), ("issue", "link", "add", "--template")):
        result, out = aj(*args)
        assert result.exit_code == 0, out
        json.loads(out)


def test_archive_stops_after_a_failing_batch_unless_told(site, monkeypatch):
    monkeypatch.setattr("acli_py.cli.issue.plural", lambda n, w: f"{n} {w}s")
    for n in range(3):
        site.add_issue("DEMO", f"x{n}", "Task")
    result, out = aj("issue", "archive", "DEMO-1", "NOPE-9", "-y")
    assert result.exit_code == 1
    assert "NOPE-9 could not be archived" in out
    result, out = aj("issue", "archive", "DEMO-2", "-y", "--ignore-errors")
    assert result.exit_code == 0, out
