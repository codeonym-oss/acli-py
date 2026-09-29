from __future__ import annotations

import keyring
import pytest
from keyring.backend import KeyringBackend

from acli_py.infrastructure import credentials
from acli_py.infrastructure.config import config_dir

NAME = "a@b.c@site.atlassian.net"


class MemoryKeyring(KeyringBackend):
    """A keyring that keeps passwords in a dict."""

    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        self.store.pop((service, username), None)


@pytest.fixture
def memory_keyring(monkeypatch):
    backend = MemoryKeyring()
    previous = keyring.get_keyring()
    keyring.set_keyring(backend)
    monkeypatch.setenv("ACLI_PY_CREDENTIAL_BACKEND", "keyring")
    yield backend
    keyring.set_keyring(previous)


def test_file_backend_round_trip_and_delete():
    assert credentials.save_token(NAME, "secret") == credentials.FILE
    assert credentials.save_token("other", "two") == credentials.FILE
    assert credentials.load_token(NAME, credentials.FILE) == "secret"
    credentials.delete_token(NAME)
    assert credentials.load_token(NAME, credentials.FILE) is None
    credentials.delete_token("other")
    assert not (config_dir() / "credentials.json").exists()
    assert "owner-only file" in credentials.describe(credentials.FILE)


def test_env_token_wins_and_is_never_stored(monkeypatch):
    monkeypatch.setenv("ACLI_PY_API_TOKEN", "from-env")
    assert credentials.load_token(NAME, credentials.FILE) == "from-env"
    assert not (config_dir() / "credentials.json").exists()


def test_keyring_backend(memory_keyring):
    assert credentials.save_token(NAME, "secret") == credentials.KEYRING
    assert memory_keyring.store == {(credentials.SERVICE, NAME): "secret"}
    assert credentials.load_token(NAME, credentials.KEYRING) == "secret"
    assert not (config_dir() / "credentials.json").exists()
    assert credentials.describe(credentials.KEYRING).startswith("system keyring")
    credentials.delete_token(NAME)
    assert memory_keyring.store == {}


def test_forcing_an_unusable_keyring_fails(monkeypatch):
    from keyring.backends import fail

    previous = keyring.get_keyring()
    keyring.set_keyring(fail.Keyring())
    monkeypatch.setenv("ACLI_PY_CREDENTIAL_BACKEND", "keyring")
    try:
        with pytest.raises(credentials.CredentialError, match="no usable keyring"):
            credentials.save_token(NAME, "secret")
    finally:
        keyring.set_keyring(previous)
