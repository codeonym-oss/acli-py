r"""Non-secret settings: the accounts you logged in with, which one is active, and defaults.

Stored as JSON in the user config directory (ACLI_PY_CONFIG_DIR overrides it):
  Linux    ~/.config/acli-py/config.json
  macOS    ~/Library/Application Support/acli-py/config.json
  Windows  %LOCALAPPDATA%\\acli-py\\config.json
API tokens are never written here; see credentials.py.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_config_dir

from acli_py.client import site_host

APP_NAME = "acli-py"
CONFIG_VERSION = 1

# The defaults `acli-py config set` accepts, and what each one means.
SETTINGS = {
    "project": "Project key used when a command needs one and none is given.",
    "issue-type": "Issue type `acli-py issue create` uses when --type is omitted.",
    "board": "Board id used by sprint commands when --board is omitted.",
    "editor": "Editor for --editor (else $VISUAL, then $EDITOR).",
}


def config_dir() -> Path:
    """Return the settings directory (ACLI_PY_CONFIG_DIR overrides the platform default)."""
    override = os.environ.get("ACLI_PY_CONFIG_DIR")
    return Path(override) if override else Path(user_config_dir(APP_NAME, appauthor=False))


def ensure_private_dir(path: Path) -> Path:
    """Create `path` if needed, owner-only on POSIX."""
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        path.chmod(stat.S_IRWXU)
    return path


def write_private_file(path: Path, text: str) -> None:
    """Write `text` to `path` atomically, readable by the owner only.

    0600 on POSIX; on Windows the per-user profile directory's ACL is what keeps it private.
    """
    ensure_private_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        if os.name == "posix":
            os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@dataclass
class Account:
    """One Atlassian account on one Jira site."""

    url: str
    email: str
    account_id: str = ""
    display_name: str = ""
    time_zone: str = ""
    token_backend: str = ""

    @property
    def host(self) -> str:
        """Return the site's host name."""
        return site_host(self.url)

    @property
    def name(self) -> str:
        """Return the account's key in the config: email@host."""
        return f"{self.email}@{self.host}"

    @classmethod
    def from_json(cls, data: dict) -> Account:
        """Build from the saved JSON form, ignoring unknown keys."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Config:
    """Every account, which one is active, and the user's defaults."""

    active: str | None = None
    accounts: dict[str, Account] = field(default_factory=dict)
    defaults: dict[str, str] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        """Return the path of config.json."""
        return config_dir() / "config.json"

    @property
    def account(self) -> Account | None:
        """Return the active account, if any."""
        return self.accounts.get(self.active) if self.active else None

    def find(self, site: str | None = None, email: str | None = None) -> list[Account]:
        """Return the accounts matching a site and/or an email (case-insensitive)."""
        host = site_host(site).lower() if site else None
        return [
            a
            for a in self.accounts.values()
            if (host is None or a.host.lower() == host)
            and (email is None or a.email.lower() == email.lower())
        ]

    @classmethod
    def load(cls) -> Config:
        """Read config.json, or return an empty config when there is none."""
        path = config_dir() / "config.json"
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        accounts = {
            name: Account.from_json(value) for name, value in data.get("accounts", {}).items()
        }
        return cls(data.get("active"), accounts, dict(data.get("defaults", {})))

    def save(self) -> None:
        """Write config.json atomically, owner-only."""
        data = {
            "version": CONFIG_VERSION,
            "active": self.active,
            "accounts": {name: asdict(account) for name, account in self.accounts.items()},
            "defaults": self.defaults,
        }
        write_private_file(self.path, json.dumps(data, indent=2) + "\n")
