"""`acli-py project`: list, view, create, update, archive, restore and delete projects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.markup import escape

from acli_py.application.commands.archive_project.command import ArchiveProject
from acli_py.application.commands.create_project.command import CreateProject
from acli_py.application.commands.delete_project.command import DeleteProject
from acli_py.application.commands.restore_project.command import RestoreProject
from acli_py.application.commands.update_project.command import UpdateProject
from acli_py.application.queries.get_project.query import GetProject
from acli_py.application.queries.list_components.query import ListComponents
from acli_py.application.queries.list_projects.query import ListProjects
from acli_py.application.queries.list_versions.query import ListVersions
from acli_py.domain.projects import TEMPLATES, ProjectSpec
from acli_py.presentation import output
from acli_py.presentation.cli.common import (
    AllOpt,
    CsvOpt,
    DryRunOpt,
    JsonOpt,
    LimitOpt,
    OutputOpt,
    WebOpt,
    YesOpt,
    connect,
    fmt,
    guarded,
    limit_of,
    open_url,
    run_many,
)
from acli_py.presentation.output import Column, dig

app = typer.Typer(help="Work with projects.", no_args_is_help=True)
KeyArg = Annotated[str, typer.Argument(help="Project key, e.g. DEMO.")]

PROJECT_TEMPLATE = {
    "key": "DEMO",
    "name": "Demo project",
    "template": "kanban",
    "lead": "@me",
    "description": "What this project is for.",
    "url": "https://example.com",
}

PROJECT_COLUMNS = [
    Column("Key", lambda p: p["key"], style="cyan", no_wrap=True),
    Column("Name", lambda p: p["name"], style="bold"),
    Column("Type", lambda p: p["projectTypeKey"]),
    Column("Style", lambda p: p["style"]),
    Column("Lead", lambda p: dig(p, "lead", "name")),
    Column("Id", lambda p: p["id"], style="dim"),
]


@app.command("list")
@guarded
def list_(
    query: Annotated[
        str | None, typer.Option("--query", "-q", help="Only projects whose key or name match.")
    ] = None,
    recent: Annotated[
        bool, typer.Option("--recent", help="Up to 20 projects you viewed recently.")
    ] = False,
    archived: Annotated[bool, typer.Option("--archived", help="Only archived projects.")] = False,
    deleted: Annotated[bool, typer.Option("--trashed", help="Only projects in the trash.")] = False,
    limit: LimitOpt = 50,
    all_pages: AllOpt = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    out: OutputOpt = None,
) -> None:
    """List the projects you can see."""
    session = connect()
    status = "archived" if archived else "deleted" if deleted else "live"
    view = session.send(ListProjects(query, status, limit_of(limit, all_pages), recent=recent))
    output.emit(
        view.to_json(), PROJECT_COLUMNS, fmt(as_json, as_csv, out), empty="No projects found."
    )


@app.command()
@guarded
def view(key: KeyArg, web: WebOpt = False, as_json: JsonOpt = False) -> None:
    """Show a project's details, issue types and components."""
    session = connect()
    if web:
        open_url(f"{session.url}/browse/{key.upper()}")
        return
    found = session.send(GetProject(key))
    if as_json:
        output.print_json(found.to_json())
        return
    project = found.project
    rows = [
        ("Name", escape(project.name)),
        ("Id", project.id),
        ("Type", project.type),
        ("Style", project.style),
        ("Lead", escape(project.lead.name if project.lead else "")),
        ("Category", escape(project.category)),
        ("URL", escape(project.url)),
        ("Description", escape(project.description)),
        ("Issue types", escape(", ".join(project.issue_types))),
        ("Components", escape(", ".join(c.name for c in project.components))),
        ("Versions", escape(", ".join(v.name for v in project.versions))),
    ]
    output.console.print(output.details(escape(project.key), rows))


@app.command()
@guarded
def create(
    key: Annotated[
        str | None, typer.Option("--key", "-k", help="New project key, e.g. DEMO.")
    ] = None,
    name: Annotated[str | None, typer.Option("--name", help="Project name.")] = None,
    template: Annotated[
        str | None,
        typer.Option(
            "--template",
            "-T",
            help=f"{', '.join(TEMPLATES)}, or a full Jira template key. Default: kanban.",
        ),
    ] = None,
    lead: Annotated[str | None, typer.Option("--lead", help="Project lead (default: you).")] = None,
    description: Annotated[
        str | None, typer.Option("--description", "-d", help="Description.")
    ] = None,
    url: Annotated[str | None, typer.Option("--url", help="A web address for the project.")] = None,
    from_json: Annotated[
        Path | None, typer.Option("--from-json", help="Read the details from a JSON file.")
    ] = None,
    from_project: Annotated[
        str | None,
        typer.Option(
            "--from-project",
            help="Share this company-managed project's configuration: its type, category, "
            "and permission, notification, security, issue type, screen and workflow schemes.",
        ),
    ] = None,
    print_template: Annotated[
        bool, typer.Option("--print-template", help="Print an example --from-json file.")
    ] = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Create a company-managed project.

    [dim]acli-py project create -k OPS -n "Operations" -T kanban
    acli-py project create -k WEB2 -n "Web 2" --from-project WEB[/]
    """
    if print_template:
        output.print_json(PROJECT_TEMPLATE)
        return
    given = {
        "key": key,
        "name": name,
        "template": template,
        "lead": lead,
        "description": description,
        "url": url,
    }
    spec = ProjectSpec.from_mapping(_merged(from_json, given))
    like = from_project.upper() if from_project else None
    session = connect(dry_run)

    def described(result: Any) -> str:
        if shares := result.after.get("shares"):
            output.info(f"Sharing {escape(like or '')}'s configuration: {', '.join(shares)}.")
        return "" if session.dry_run else escape(result.after.get("name") or "")

    run_many(
        session,
        [CreateProject(spec, like)],
        done="would be created" if session.dry_run else "created",
        as_json=as_json,
        describe=described,
    )


@app.command()
@guarded
def update(
    project: KeyArg,
    key: Annotated[str | None, typer.Option("--key", "-k", help="New key.")] = None,
    name: Annotated[str | None, typer.Option("--name", help="New name.")] = None,
    lead: Annotated[str | None, typer.Option("--lead", help="New lead.")] = None,
    description: Annotated[
        str | None, typer.Option("--description", "-d", help="New description.")
    ] = None,
    url: Annotated[str | None, typer.Option("--url", help="New URL.")] = None,
    from_json: Annotated[
        Path | None, typer.Option("--from-json", help="Read the changes from a JSON file.")
    ] = None,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Change a project's key, name, lead, description or URL."""
    given = {"key": key, "name": name, "lead": lead, "description": description, "url": url}
    command = UpdateProject(project, ProjectSpec.from_mapping(_merged(from_json, given)))
    session = connect(dry_run)
    run_many(
        session,
        [command],
        done="would be updated" if session.dry_run else "updated",
        yes=yes,
        as_json=as_json,
    )


def _merged(from_json: Path | None, given: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON file's members, overridden by the options given."""
    data = json.loads(from_json.read_text(encoding="utf-8")) if from_json else {}
    data.update({k: v for k, v in given.items() if v is not None})
    return data


@app.command()
@guarded
def delete(
    key: KeyArg,
    permanent: Annotated[
        bool, typer.Option("--permanent", help="Skip the trash: cannot be undone.")
    ] = False,
    yes: YesOpt = False,
    dry_run: DryRunOpt = False,
) -> None:
    """Move a project to the trash (restorable for 60 days), or delete it for good."""
    session = connect(dry_run)
    done = "deleted permanently" if permanent else "moved to the trash"
    run_many(
        session,
        [DeleteProject(key, permanent)],
        done=f"would be {done}" if session.dry_run else done,
        yes=yes,
    )


@app.command()
@guarded
def archive(key: KeyArg, yes: YesOpt = False, dry_run: DryRunOpt = False) -> None:
    """Archive a project (read-only, restorable)."""
    session = connect(dry_run)
    run_many(
        session,
        [ArchiveProject(key)],
        done="would be archived" if session.dry_run else "archived",
        yes=yes,
    )


@app.command()
@guarded
def restore(key: KeyArg, yes: YesOpt = False, dry_run: DryRunOpt = False) -> None:
    """Restore a project from the trash or the archive."""
    session = connect(dry_run)
    run_many(
        session,
        [RestoreProject(key)],
        done="would be restored" if session.dry_run else "restored",
        yes=yes,
    )


@app.command()
@guarded
def components(
    key: KeyArg, as_json: JsonOpt = False, as_csv: CsvOpt = False, out: OutputOpt = None
) -> None:
    """List a project's components."""
    found = connect().send(ListComponents(key))
    output.emit(
        found.to_json(),
        [
            Column("Id", lambda c: c["id"], style="dim"),
            Column("Name", lambda c: c["name"], style="bold"),
            Column("Lead", lambda c: dig(c, "lead", "name")),
            Column("Description", lambda c: c["description"]),
        ],
        fmt(as_json, as_csv, out),
        empty=f"{found.key} has no components.",
    )


@app.command()
@guarded
def versions(
    key: KeyArg,
    unreleased: Annotated[
        bool, typer.Option("--unreleased", help="Hide released versions.")
    ] = False,
    as_json: JsonOpt = False,
    as_csv: CsvOpt = False,
    out: OutputOpt = None,
) -> None:
    """List a project's versions (releases)."""
    found = connect().send(ListVersions(key, unreleased))
    output.emit(
        found.to_json(),
        [
            Column("Id", lambda v: v["id"], style="dim"),
            Column("Name", lambda v: v["name"], style="bold"),
            Column("Released", lambda v: "yes" if v["released"] else ""),
            Column("Archived", lambda v: "yes" if v["archived"] else ""),
            Column("Start", lambda v: v["startDate"]),
            Column("Release", lambda v: v["releaseDate"]),
            Column("Description", lambda v: v["description"]),
        ],
        fmt(as_json, as_csv, out),
        empty=f"{found.key} has no versions.",
    )
