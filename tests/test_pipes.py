"""Pipes: `-` reads issues from stdin, `--output keys|jsonl`, asking mid-pipe, `| head`."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys

import pytest

from acli_py.presentation import inputs, output, terminal
from acli_py.presentation.cli import common
from acli_py.presentation.inputs import InputError
from acli_py.presentation.output import Column, Format, pick_format
from tests import fake_jira
from tests.conftest import run_cli

REAL_OPEN_TTY = terminal.open_tty  # the test run swaps in a stand-in (see conftest)
posix_only = pytest.mark.skipif(os.name != "posix", reason="needs POSIX pipes and sessions")


# ── reading issues ───────────────────────────────────────────────────────────


def test_keys_in_reads_plain_keys_json_lines_and_json_arrays():
    assert inputs.keys_in("demo-1, DEMO-2\n# a comment\nDEMO-3 # trailing\n\n") == [
        "DEMO-1", "DEMO-2", "DEMO-3",
    ]  # fmt: skip
    jsonl = '{"key": "DEMO-1", "fields": {}}\n{"id": 10042}\n'
    assert inputs.keys_in(jsonl) == ["DEMO-1", "10042"]
    assert inputs.keys_in('[{"key": "demo-1"}, "DEMO-2", {"key": "DEMO-1"}]') == [
        "DEMO-1", "DEMO-2",
    ]  # fmt: skip
    assert inputs.keys_in("") == []


def test_keys_in_says_what_is_wrong():
    with pytest.raises(InputError, match="line 2 starts like JSON"):
        inputs.keys_in('{"key": "DEMO-1"}\n{"key": \n')
    with pytest.raises(InputError, match="JSON array but isn't valid"):
        inputs.keys_in("[1, 2")
    with pytest.raises(InputError, match="has no key or id"):
        inputs.keys_in('{"summary": "no key"}')


def test_a_dash_reads_issues_from_stdin(site):
    piped = '{"key": "DEMO-1"}\n{"key": "DEMO-2"}\n'
    result, out = run_cli("issue", "transition", "-", "--to", "Done", "-y", input=piped)
    assert result.exit_code == 0, out
    assert "2 of 2 moved." in out
    assert site.issues["DEMO-2"]["fields"]["status"]["name"] == "Done"


def test_an_empty_pipe_picks_nothing(site):
    result, out = run_cli("issue", "transition", "-", "--to", "Done", "-y", input="")
    assert result.exit_code == 0, out
    assert "No issues match; nothing to move." in out
    result, out = run_cli("issue", "transition", "--to", "Done", "-y")
    assert result.exit_code == 1
    assert "'-' for stdin" in out


def test_filter_owner_reads_ids_from_stdin(site):
    piped = json.dumps({"id": "10100", "name": "My open work"}) + "\n"
    result, out = run_cli("filter", "owner", "-", "--to", "bob@example.com", "-y", input=piped)
    assert result.exit_code == 0, out
    assert site.filters["10100"]["owner"] == fake_jira.BOB


# ── printing for the next command ────────────────────────────────────────────


def test_output_keys_and_jsonl_print_one_per_line(site):
    result, out = run_cli("issue", "search", "project = DEMO", "--output", "keys")
    assert result.exit_code == 0, out
    assert out.splitlines() == ["DEMO-1", "DEMO-2", "DEMO-3"]
    result, out = run_cli("issue", "search", "project = DEMO", "--output", "jsonl")
    assert [json.loads(line)["key"] for line in out.splitlines()] == ["DEMO-1", "DEMO-2", "DEMO-3"]
    result, out = run_cli("project", "list", "--output", "keys")
    assert "DEMO" in out.splitlines()


def test_output_conflicts_with_json_and_csv():
    assert pick_format(False, False, Format.keys) is Format.keys
    assert pick_format(True, False, Format.json) is Format.json
    with pytest.raises(ValueError, match="choose one of --json, --csv and --output"):
        pick_format(True, False, Format.jsonl)
    with pytest.raises(ValueError, match="choose one"):
        pick_format(True, True)


def test_key_of_names_any_row(capsys):
    assert output.key_of({"key": "DEMO-1", "id": "1"}) == "DEMO-1"
    assert output.key_of({"id": 7}) == "7"
    assert output.key_of({"accountId": "abc"}) == "abc"
    assert output.key_of({"name": "High"}) == "High"
    assert output.key_of({"other": 1}) == ""
    assert output.key_of("plain") == "plain"
    output.emit([{"name": "High"}], [Column("Name", lambda r: r["name"])], Format.keys)
    assert capsys.readouterr().out == "High\n"


# ── asking mid-pipe ──────────────────────────────────────────────────────────


class FakeTty:
    """Stands in for `open_tty`: answers from a script, keeping what it was asked."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.asked = ""

    def __call__(self) -> tuple[io.StringIO, io.StringIO]:
        tty = self

        class Writer(io.StringIO):
            def write(self, text: str) -> int:
                tty.asked += text
                return len(text)

        return io.StringIO(self.answer), Writer()


def test_asks_on_the_terminal_when_stdin_is_a_pipe(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("DEMO-1\n"))
    tty = FakeTty("y\n")
    monkeypatch.setattr(terminal, "open_tty", tty)
    assert terminal.available()
    assert terminal.ask("Move DEMO-1 to Done?")
    assert tty.asked == "Move DEMO-1 to Done? [y/N]: "
    monkeypatch.setattr(terminal, "open_tty", FakeTty("\n"))
    assert not terminal.ask("Move DEMO-1 to Done?")  # no by default


def test_a_piped_command_asks_on_the_terminal(site, monkeypatch):
    tty = FakeTty("yes\n")
    monkeypatch.setattr(terminal, "open_tty", tty)
    result, out = run_cli("issue", "transition", "-", "--to", "Done", input="DEMO-1\nDEMO-3\n")
    assert result.exit_code == 0, out
    assert tty.asked == "Move 2 issues (DEMO-1, DEMO-3) to Done? [y/N]: "
    assert "Login fails on Safari" in out  # the preview, shown before asking
    assert site.issues["DEMO-3"]["fields"]["status"]["name"] == "Done"


def test_no_terminal_means_no(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert not terminal.available()
    assert not terminal.ask("Move DEMO-1 to Done?")
    assert not common.interactive()


def test_open_tty_gives_up_without_a_terminal(monkeypatch, tmp_path):
    monkeypatch.setattr(terminal, "open_tty", REAL_OPEN_TTY)
    monkeypatch.setattr(terminal, "TTY", (str(tmp_path / "none"), str(tmp_path / "none")))
    assert terminal.open_tty() is None
    (tmp_path / "in").write_text("y\n")
    monkeypatch.setattr(terminal, "TTY", (str(tmp_path / "in"), str(tmp_path / "no" / "out")))
    assert terminal.open_tty() is None
    monkeypatch.setattr(terminal, "TTY", (str(tmp_path / "in"), str(tmp_path / "out")))
    reader, writer = terminal.open_tty() or (None, None)
    assert reader is not None and writer is not None  # noqa: PT018 - one pair
    reader.close()
    writer.close()


def test_a_broken_pipe_exits_quietly(site, monkeypatch):
    def gone(*args, **kwargs):
        raise BrokenPipeError(32, "Broken pipe")

    monkeypatch.setattr(output, "emit", gone)
    result, out = run_cli("issue", "search", "project = DEMO", "--output", "keys")
    assert result.exit_code == common.EXIT_BROKEN_PIPE
    assert out == ""


def test_rich_leaves_a_broken_pipe_to_the_guard():
    console = output._Stdout(file=io.StringIO())
    with pytest.raises(BrokenPipeError):
        console.on_broken_pipe()
    assert console.quiet


# ── real pipelines against the fake site ─────────────────────────────────────


@pytest.fixture
def shell_env(fake, jira, tmp_path):
    """The environment of a real `acli-py` process logged in to the fake site."""
    return {
        **os.environ,
        "ACLI_PY_SITE": fake[1],
        "ACLI_PY_EMAIL": fake_jira.EMAIL,
        "ACLI_PY_API_TOKEN": fake_jira.TOKEN,
        "ACLI_PY_CONFIG_DIR": str(tmp_path / "config"),
        "ACLI_PY_CREDENTIAL_BACKEND": "file",
        "PYTHONIOENCODING": "utf-8",
        "NO_COLOR": "1",
    }


def acli(*args: str) -> list[str]:
    return [sys.executable, "-m", "acli_py", *args]


def pipeline(env: dict, first: list[str], second: list[str], **options) -> tuple:
    """Run `first | second`; return (first's exit, second's exit, second's stdout+stderr)."""
    upstream = subprocess.Popen(first, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    downstream = subprocess.run(
        second, stdin=upstream.stdout, capture_output=True, text=True, env=env, timeout=60,
        **options,
    )  # fmt: skip
    assert upstream.stdout is not None
    upstream.stdout.close()
    return upstream.wait(timeout=60), downstream.returncode, downstream.stdout + downstream.stderr


def test_search_keys_piped_into_transition(shell_env, jira):
    first = acli("issue", "search", "project = DEMO", "--output", "keys")
    up, down, out = pipeline(
        shell_env, first, acli("issue", "transition", "-", "--to", "Done", "-y")
    )
    assert (up, down) == (0, 0), out
    assert "3 of 3 moved." in out
    assert {i["fields"]["status"]["name"] for i in jira.issues.values()
            if i["key"].startswith("DEMO")} == {"Done"}  # fmt: skip


def test_search_jsonl_piped_into_transition(shell_env, jira):
    first = acli("issue", "search", "key in (DEMO-1)", "--output", "jsonl")
    up, down, out = pipeline(
        shell_env, first, acli("issue", "transition", "-", "--to", "In Progress", "-y")
    )
    assert (up, down) == (0, 0), out
    assert "DEMO-1 moved to In Progress" in out


@posix_only
def test_mid_pipe_without_a_terminal_needs_yes(shell_env, jira):
    first = acli("issue", "search", "project = DEMO", "--output", "keys")
    second = acli("issue", "transition", "-", "--to", "Done")
    # A new session has no controlling terminal: nobody to ask.
    _, down, out = pipeline(shell_env, first, second, start_new_session=True)
    assert down == common.EXIT_ABORTED, out
    assert "Refusing without --yes" in out
    assert jira.writes() == []


@posix_only
def test_a_reader_that_stops_early_is_not_an_error(shell_env):
    process = subprocess.Popen(
        acli("issue", "search", "project = DEMO", "--output", "jsonl"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=shell_env,
    )  # fmt: skip
    assert process.stdout is not None and process.stderr is not None  # noqa: PT018
    process.stdout.close()  # like `| head` exiting before the first line arrives
    errors = process.stderr.read()
    process.stderr.close()
    assert process.wait(timeout=60) == common.EXIT_BROKEN_PIPE
    assert errors == b""
