"""Where API tokens live.

First choice is the operating system's credential store through `keyring`:
Windows Credential Manager, macOS Keychain, or the Secret Service (GNOME
Keyring, KWallet) on Linux. When none is usable (a headless server, WSL, a
container) the token goes to `credentials.json` in the config directory,
created 0600 inside a 0700 directory.

ACLI_PY_CREDENTIAL_BACKEND=file|keyring forces a backend. ACLI_PY_API_TOKEN, when set,
is used instead of the stored token (for CI), and is never stored.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from acli_py.infrastructure.config import config_dir, write_private_file

if TYPE_CHECKING:
    from pathlib import Path

SERVICE = "acli-py"
KEYRING = "keyring"
FILE = "file"


class CredentialError(RuntimeError):
    """The token could not be stored or read."""


def _credentials_file() -> Path:
    return config_dir() / "credentials.json"


def _forced() -> str:
    return os.environ.get("ACLI_PY_CREDENTIAL_BACKEND", "").lower()


def _keyring_usable() -> bool:
    if _forced() == FILE:
        return False
    try:
        import keyring
        from keyring.backends import fail

        backend = keyring.get_keyring()
        if isinstance(backend, fail.Keyring):
            return False
        # A chainer with no real backends behind it cannot store anything.
        return getattr(backend, "priority", 1) > 0
    except Exception:
        return False


def _read_file() -> dict[str, str]:
    path = _credentials_file()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_token(name: str, token: str) -> str:
    """Store the token for account `name` (email@host), returning the backend used."""
    if _forced() == KEYRING and not _keyring_usable():
        raise CredentialError(
            "ACLI_PY_CREDENTIAL_BACKEND=keyring but no usable keyring backend was found"
        )
    if _keyring_usable():
        try:
            import keyring

            keyring.set_password(SERVICE, name, token)
            return KEYRING
        except Exception:
            if _forced() == KEYRING:
                raise
    stored = _read_file()
    stored[name] = token
    write_private_file(_credentials_file(), json.dumps(stored, indent=2) + "\n")
    return FILE


def load_token(name: str, backend: str) -> str | None:
    """Return the stored token (or ACLI_PY_API_TOKEN), or None when there is none."""
    if env := os.environ.get("ACLI_PY_API_TOKEN"):
        return env
    if backend == KEYRING:
        try:
            import keyring

            return keyring.get_password(SERVICE, name)
        except Exception as error:
            raise CredentialError(
                f"could not read the token from the system keyring: {error}"
            ) from error
    return _read_file().get(name)


def delete_token(name: str) -> None:
    """Remove the token from every backend it may be in."""
    if _forced() != FILE:
        try:
            import keyring

            keyring.delete_password(SERVICE, name)
        except Exception:
            pass
    path = _credentials_file()
    if path.exists():
        stored = _read_file()
        stored.pop(name, None)
        if stored:
            write_private_file(path, json.dumps(stored, indent=2) + "\n")
        else:
            path.unlink()


def describe(backend: str) -> str:
    """Return a human description of where a token is kept."""
    if backend == KEYRING:
        try:
            import keyring

            return f"system keyring ({type(keyring.get_keyring()).__module__.split('.')[-1]})"
        except Exception:
            return "system keyring"
    return f"{_credentials_file()} (owner-only file)"
