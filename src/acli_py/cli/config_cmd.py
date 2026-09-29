"""`aj config`: defaults such as the project and the issue type."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.markup import escape

from acli_py import output
from acli_py.cli.common import JsonOpt, fail, guarded
from acli_py.config import SETTINGS, Config

app = typer.Typer(help="Show or change your defaults.", no_args_is_help=True)

SettingArg = Annotated[str, typer.Argument(help=f"One of: {', '.join(SETTINGS)}.")]


def _setting(name: str) -> str:
    name = name.strip().lower().replace("_", "-")
    if name not in SETTINGS:
        raise fail(f"Unknown setting {escape(name)!r}. Known: {', '.join(SETTINGS)}.")
    return name


@app.command()
@guarded
def show(as_json: JsonOpt = False) -> None:
    """Show every setting, the active account and where the config lives."""
    config = Config.load()
    if as_json:
        output.print_json(
            {"active": config.active, "defaults": config.defaults, "path": str(config.path)}
        )
        return
    rows = [("account", escape(config.active or "—  run aj auth login"))]
    rows += [
        (name, escape(config.defaults.get(name, "")) or f"[dim]unset · {SETTINGS[name]}[/]")
        for name in SETTINGS
    ]
    rows.append(("file", f"[dim]{escape(str(config.path))}[/]"))
    output.console.print(output.details("acli-py config", rows))


@app.command("set")
@guarded
def set_(name: SettingArg, value: Annotated[str, typer.Argument(help="The value.")]) -> None:
    """Set a default, e.g. `aj config set project DEMO`."""
    name = _setting(name)
    config = Config.load()
    config.defaults[name] = value.upper() if name == "project" else value
    config.save()
    output.success(f"{name} = {escape(config.defaults[name])}")


@app.command()
@guarded
def unset(name: SettingArg) -> None:
    """Remove a default."""
    name = _setting(name)
    config = Config.load()
    if config.defaults.pop(name, None) is None:
        output.info(f"{name} was not set.")
        return
    config.save()
    output.success(f"{name} unset")


@app.command()
def path() -> None:
    """Print where the config file lives."""
    output.console.print(str(Config.load().path), soft_wrap=True, highlight=False)
