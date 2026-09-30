from __future__ import annotations

import pytest
import typer.testing
from typer.testing import CliRunner

from acli_py.presentation import terminal
from acli_py.presentation.cli import app
from tests import fake_jira

runner = CliRunner()

# Building the Click tree from ~90 command signatures takes most of each invocation; the tree
# never changes, so build it once. (Private Typer API: without it tests are just slower.)
_original = getattr(typer.testing, "_get_command", None)
if _original is not None:
    _build = _original
    _command = _build(app)
    setattr(  # noqa: B010
        typer.testing,
        "_get_command",
        lambda typer_app: _command if typer_app is app else _build(typer_app),
    )


def run_cli(*args: str, input: str | None = None):
    """Run `acli-py` in-process; return (result, combined stdout+stderr)."""
    result = runner.invoke(app, list(args), input=input)
    return result, result.output


@pytest.fixture(scope="session")
def fake():
    server, jira, url = fake_jira.start()
    yield jira, url
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Every test gets its own config directory and the file credential backend."""
    monkeypatch.setenv("ACLI_PY_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ACLI_PY_CREDENTIAL_BACKEND", "file")
    for name in ("ACLI_PY_API_TOKEN", "ACLI_PY_SITE", "ACLI_PY_EMAIL", "ACLI_PY_DRY_RUN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("COLUMNS", "200")
    # Never ask on the real terminal behind the test run: tests are the "no terminal" case.
    monkeypatch.setattr(terminal, "open_tty", lambda: None)
    return tmp_path


@pytest.fixture
def jira(fake):
    """The fake site, reset to its seed data, with nobody logged in."""
    state, _ = fake
    state.reset()
    return state


@pytest.fixture
def site(fake, jira):
    """Log in to the fake site; return its state (the request log starts empty)."""
    _, url = fake
    result, out = run_cli(
        "auth", "login", "--site", url, "--email", fake_jira.EMAIL, "--token", fake_jira.TOKEN
    )
    assert result.exit_code == 0, out
    jira.log.clear()
    return jira
