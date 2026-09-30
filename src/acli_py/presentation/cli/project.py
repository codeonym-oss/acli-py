"""`acli-py project`: list, view, create, update, archive, restore and delete projects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.markup import escape

from acli_py.infrastructure.jira import resolve
from acli_py.infrastructure.jira.client import API, NotFoundError
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
    confirm,
    connect,
    fail,
    fmt,
    guarded,
    limit_of,
    open_url,
)
from acli_py.presentation.output import Column, dig

app = typer.Typer(help="Work with projects.", no_args_is_help=True)
KeyArg = Annotated[str, typer.Argument(help="Project key, e.g. DEMO.")]

# Friendly names for Jira's company-managed project templates.
GREENHOPPER = "com.pyxis.greenhopper.jira:gh-simplified-"
CORE = "com.atlassian.jira-core-project-templates:jira-core-simplified-"
TEMPLATES = {
    "scrum": ("software", f"{GREENHOPPER}scrum-classic"),
    "kanban": ("software", f"{GREENHOPPER}kanban-classic"),
    "basic": ("software", f"{GREENHOPPER}basic"),
    "tasks": ("business", f"{CORE}task-tracking"),
    "process": ("business", f"{CORE}process-control"),
    "service": ("service_desk", "com.atlassian.servicedesk:simplified-it-service-management"),
}

PROJECT_TEMPLATE = {
    "key": "DEMO",
    "name": "Demo project",
    "template": "kanban",
    "lead": "@me",
    "description": "What this project is for.",
    "url": "https://example.com",
}

PROJECT_COLUMNS = [
    Column("Key", lambda p: p.get("key"), style="cyan", no_wrap=True),
    Column("Name", lambda p: p.get("name"), style="bold"),
    Column("Type", lambda p: p.get("projectTypeKey")),
    Column("Style", lambda p: p.get("style")),
    Column("Lead", lambda p: dig(p, "lead", "displayName")),
    Column("Id", lambda p: p.get("id"), style="dim"),
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
    if recent:
        projects = session.client.get(f"{API}/project/recent", expand="lead")
    else:
        action = ["archived"] if archived else ["deleted"] if deleted else ["live"]
        projects = list(
            session.client.paged(
                f"{API}/project/search",
                limit=limit_of(limit, all_pages),
                query=query,
                orderBy="key",
                expand="lead",
                status=",".join(action),
            )
        )
    output.emit(projects, PROJECT_COLUMNS, fmt(as_json, as_csv, out), empty="No projects found.")


@app.command()
@guarded
def view(key: KeyArg, web: WebOpt = False, as_json: JsonOpt = False) -> None:
    """Show a project's details, issue types and components."""
    session = connect()
    if web:
        open_url(f"{session.url}/browse/{key.upper()}")
        return
    project = session.client.get(
        f"{API}/project/{key.upper()}", expand="lead,description,issueTypes,url,projectKeys"
    )
    if as_json:
        output.print_json(project)
        return
    rows = [
        ("Name", escape(project.get("name", ""))),
        ("Id", project.get("id")),
        ("Type", project.get("projectTypeKey")),
        ("Style", project.get("style")),
        ("Lead", escape(dig(project, "lead", "displayName", default=""))),
        ("Category", escape(dig(project, "projectCategory", "name", default=""))),
        ("URL", escape(project.get("url") or "")),
        ("Description", escape(project.get("description") or "")),
        ("Issue types", escape(", ".join(t["name"] for t in project.get("issueTypes", [])))),
        ("Components", escape(", ".join(c["name"] for c in project.get("components", [])))),
        ("Versions", escape(", ".join(v["name"] for v in project.get("versions", [])))),
    ]
    output.console.print(output.details(escape(project.get("key", key)), rows))


# Where to read each scheme a project uses: (body field, path, key in a values entry).
_SCHEMES_BY_PROJECT = (
    ("issueTypeScheme", "issuetypescheme/project", "issueTypeScheme"),
    ("issueTypeScreenScheme", "issuetypescreenscheme/project", "issueTypeScreenScheme"),
    ("workflowScheme", "workflowscheme/project", "workflowScheme"),
)


def shared_configuration(client: Any, key: str) -> dict[str, Any]:
    """Return the POST /project fields that make a new project share `key`'s configuration."""
    source = client.get(f"{API}/project/{key.upper()}")
    if source.get("style") == "next-gen" or source.get("simplified"):
        raise fail(
            f"{escape(key.upper())} is team-managed; only company-managed projects "
            "can share their configuration."
        )
    shared: dict[str, Any] = {"projectTypeKey": source.get("projectTypeKey", "software")}
    if category := (source.get("projectCategory") or {}).get("id"):
        shared["categoryId"] = int(category)
    for field_name, path in (
        ("permissionScheme", "permissionscheme"),
        ("notificationScheme", "notificationscheme"),
        ("issueSecurityScheme", "issuesecuritylevelscheme"),
    ):
        try:
            scheme = client.get(f"{API}/project/{key.upper()}/{path}")
        except NotFoundError:  # no issue security scheme, say
            continue
        if scheme and scheme.get("id") is not None:
            shared[field_name] = int(scheme["id"])
    for field_name, path, inner in _SCHEMES_BY_PROJECT:
        values = client.get(f"{API}/{path}", projectId=source["id"]).get("values") or []
        scheme_id = (values[0].get(inner) or {}).get("id") if values else None
        if scheme_id is not None:
            shared[field_name] = int(scheme_id)
    return shared


def _project_body(
    session: Any, data: dict[str, Any], creating: bool, *, schemes: bool = False
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for src, dest in (
        ("key", "key"),
        ("name", "name"),
        ("description", "description"),
        ("url", "url"),
    ):
        if data.get(src) is not None:
            body[dest] = data[src]
    if data.get("lead"):
        body["leadAccountId"] = resolve.user(session.client, data["lead"], session.me)["accountId"]
    elif creating:
        body["leadAccountId"] = session.me
    template = data.get("template")
    if template:
        type_key, template_key = TEMPLATES.get(template.lower(), (data.get("type"), template))
        body["projectTemplateKey"] = template_key
        body["projectTypeKey"] = data.get("type") or type_key
    elif data.get("type"):
        body["projectTypeKey"] = data["type"]
    if creating:
        body.setdefault("projectTypeKey", "software")
        # A template and shared schemes are two ways to configure a project: not both.
        if (
            not schemes
            and "projectTemplateKey" not in body
            and body["projectTypeKey"] == "software"
        ):
            body["projectTemplateKey"] = TEMPLATES["kanban"][1]
        body.setdefault("assigneeType", "UNASSIGNED")
    # Anything else in a JSON file is Jira's own field name: pass it through.
    known = {"key", "name", "description", "url", "lead", "template", "type"}
    body.update({k: v for k, v in data.items() if k not in known})
    return body


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
    data = json.loads(from_json.read_text(encoding="utf-8")) if from_json else {}
    given = {"key": key, "name": name, "template": template, "lead": lead,
             "description": description, "url": url}  # fmt: skip
    data.update({k: v for k, v in given.items() if v is not None})
    if not data.get("key") or not data.get("name"):
        raise fail("A new project needs [bold]--key[/] and [bold]--name[/].")
    data["key"] = data["key"].upper()
    session = connect(dry_run)
    shared: dict[str, Any] = {}
    if from_project:
        shared = shared_configuration(session.client, from_project)
        data.pop("template", None)
        data.setdefault("type", shared.pop("projectTypeKey"))
        copied = ", ".join(k.removesuffix("Scheme") for k in shared if k.endswith("Scheme"))
        output.info(f"Sharing {escape(from_project.upper())}'s configuration: {copied}.")
    body = _project_body(session, data, creating=True, schemes=bool(shared))
    body.update({k: v for k, v in shared.items() if k not in body})
    result = session.client.post(f"{API}/project", body)
    if as_json:
        output.print_json(result)
    if not session.dry_run:
        output.success(
            f"Created project [bold cyan]{escape(data['key'])}[/] {escape(data['name'])}"
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
    dry_run: DryRunOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Change a project's key, name, lead, description or URL."""
    data = json.loads(from_json.read_text(encoding="utf-8")) if from_json else {}
    given = {"key": key.upper() if key else None, "name": name, "lead": lead,
             "description": description, "url": url}  # fmt: skip
    data.update({k: v for k, v in given.items() if v is not None})
    if not data:
        raise fail("Nothing to change. See [bold]acli-py project update --help[/].")
    session = connect(dry_run)
    result = session.client.put(
        f"{API}/project/{project.upper()}", _project_body(session, data, creating=False)
    )
    if as_json:
        output.print_json(result)
    if not session.dry_run:
        output.success(f"Updated project {escape(project.upper())}")


def _project_action(key: str, action: str, question: str, yes: bool, dry_run: bool) -> None:
    session = connect(dry_run)
    key = key.upper()
    confirm(question.format(key=key), yes, session)
    if action == "delete":
        session.client.delete(f"{API}/project/{key}", enableUndo="true")
    elif action == "purge":
        session.client.delete(f"{API}/project/{key}", enableUndo="false")
    else:
        session.client.post(f"{API}/project/{key}/{action}")
    if not session.dry_run:
        done = {"delete": "moved to the trash", "purge": "deleted permanently",
                "archive": "archived", "restore": "restored"}[action]  # fmt: skip
        output.success(f"Project {key} {done}")


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
    if permanent:
        _project_action(key, "purge", "PERMANENTLY delete {key} and all its issues?", yes, dry_run)
    else:
        _project_action(key, "delete", "Move project {key} to the trash?", yes, dry_run)


@app.command()
@guarded
def archive(key: KeyArg, yes: YesOpt = False, dry_run: DryRunOpt = False) -> None:
    """Archive a project (read-only, restorable)."""
    _project_action(key, "archive", "Archive project {key}?", yes, dry_run)


@app.command()
@guarded
def restore(key: KeyArg, dry_run: DryRunOpt = False) -> None:
    """Restore a project from the trash or the archive."""
    _project_action(key, "restore", "", True, dry_run)


@app.command()
@guarded
def components(
    key: KeyArg, as_json: JsonOpt = False, as_csv: CsvOpt = False, out: OutputOpt = None
) -> None:
    """List a project's components."""
    session = connect()
    output.emit(
        session.client.get(f"{API}/project/{key.upper()}/components"),
        [
            Column("Id", lambda c: c.get("id"), style="dim"),
            Column("Name", lambda c: c.get("name"), style="bold"),
            Column("Lead", lambda c: dig(c, "lead", "displayName")),
            Column("Description", lambda c: c.get("description")),
        ],
        fmt(as_json, as_csv, out),
        empty=f"{key.upper()} has no components.",
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
    session = connect()
    found = session.client.get(f"{API}/project/{key.upper()}/versions")
    if unreleased:
        found = [v for v in found if not v.get("released")]
    output.emit(
        found,
        [
            Column("Id", lambda v: v.get("id"), style="dim"),
            Column("Name", lambda v: v.get("name"), style="bold"),
            Column("Released", lambda v: "yes" if v.get("released") else ""),
            Column("Archived", lambda v: "yes" if v.get("archived") else ""),
            Column("Start", lambda v: v.get("startDate")),
            Column("Release", lambda v: v.get("releaseDate")),
            Column("Description", lambda v: v.get("description")),
        ],
        fmt(as_json, as_csv, out),
        empty=f"{key.upper()} has no versions.",
    )
