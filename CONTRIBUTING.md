# Contributing to acli-py

Thanks for helping! This guide covers the local setup and the conventions CI enforces.

## Setup

You need [uv](https://docs.astral.sh/uv/). Python versions are installed by uv as needed.

```sh
git clone git@github.com:codeonym-oss/acli-py.git && cd acli-py
uv sync                                  # .venv with the locked dev tools
uv run pre-commit install --install-hooks -t pre-commit -t commit-msg -t pre-push
uv run acli-py --help                         # the CLI, from your checkout
```

The hooks run the same checks as CI:

| Stage        | Checks                                                   |
|--------------|----------------------------------------------------------|
| `pre-commit` | ruff lint + format, pyright, file hygiene                |
| `commit-msg` | the message is a [Conventional Commit](#commits)         |
| `pre-push`   | the branch name follows [`<type>/<issue>-<slug>`](#branches) |

Run the full suite with `uv run pytest`; a coverage below `fail_under` in `pyproject.toml` fails.
The tests never reach a real Jira, and every test gets its own config directory and a file
credential store.

`tests/fake_jira.py` is a stateful, in-memory Jira (platform v3 and Agile 1.0 routes) served
over real HTTP. Tests run the real `acli-py` commands against it, then check both the output and what
changed on the fake site. It records every request, which is how
`test_every_write_command_honours_dry_run` proves that `--dry-run` sends no writes. When you add
a write command, add it to that test's list.

Keep test data fictional, since the repository is public. To test another Python version:
`uv run --isolated --python 3.14 pytest`.

CI runs the tests on Linux for Python 3.11 to 3.14, and on macOS and Windows for 3.12.

## Workflow

1. **Start from an issue.** Open one first if none exists.
2. **Branch** from `main` using the [branch convention](#branches).
3. **Commit** using [Conventional Commits](#commits).
4. **Open a PR** whose [title](#pull-requests) ends with the issue key and whose body says `Fixes #N`.
5. CI must be green. PRs are **squash-merged**, so the PR title becomes the commit on `main`.

`main` is protected: no direct pushes, no force-pushes, linear history, and these required checks:
`ci-ok`, `branch-name`, `commits`, `pr-title`.

## Conventions

The allowed types are the same everywhere:

| Type       | Use for                                          | In changelog |
|------------|--------------------------------------------------|--------------|
| `feat`     | a new feature                                    | Features     |
| `fix`      | a bug fix                                        | Bug Fixes    |
| `perf`     | a performance improvement                        | Performance  |
| `docs`     | documentation only                               | Documentation|
| `build`    | packaging, dependencies, build tooling           | Build        |
| `refactor` | code change that neither fixes nor adds          | hidden       |
| `test`     | tests only                                       | hidden       |
| `ci`       | CI and release workflows                         | hidden       |
| `chore`    | repo maintenance                                 | hidden       |
| `revert`   | reverting a previous commit                      | shown        |

### Branches

`<type>/<issue>-<slug>`: a type from the table, the GitHub issue number, and a short lowercase
hyphenated slug.

```text
feat/5-export-xlsx
fix/23-week-boundary
docs/12-readme-quickstart
```

Branches opened by bots (`release-please--*`, `dependabot/*`) are exempt.

### Commits

Every commit follows [Conventional Commits 1.0](https://www.conventionalcommits.org/en/v1.0.0/):

```text
<type>(<optional scope>)<optional !>: <summary>

<optional body>

<optional footer(s)>
```

```text
feat(sprint): add `sprint start --weeks`
fix: keep labels when --add-label is repeated
feat!: rename `issue move` to `issue transition`

BREAKING CHANGE: `issue move` is now only a hidden alias.
```

- Summary in the imperative, lowercase, no trailing period.
- `!` or a `BREAKING CHANGE:` footer marks a breaking change.
- The issue key is **not** required in commit messages; the branch and PR carry it.

### Pull requests

The title is a conventional commit summary **ending with the issue key**, and the body links the
issue:

```text
feat: add worklog commands (#5)
```

```text
Fixes #5
```

Keep a PR to one issue. Fill in the PR template's checklist.

## Code layout

The code is split into four layers; [ADR 0001](docs/adr/0001-layers.md) explains why.

```text
src/acli_py/
  domain/          Jira's concepts and rules: pure Python, no I/O
  application/     use cases on the mediary bus: commands/, queries/, events/, behaviors/
  infrastructure/  the Jira client, config, credentials, files
  presentation/    cli/, shell.py, tui/, output.py
  bootstrap.py     builds the bus and the adapters for the front ends
```

Each layer imports only the layers below it (presentation → bootstrap → infrastructure →
application → domain), and front ends reach infrastructure only through `bootstrap`.
`uv run lint-imports` checks this in pre-commit and CI. Code written before the layers is
listed under `ignore_imports` in `pyproject.toml`; when you move a use case, delete its lines
there. Never add new ones.

### Adding a command

A command changes Jira. Give it its own folder, named after what it does:

```text
application/commands/watch_issue/
  __init__.py
  command.py    # the message
  handler.py    # what it does
```

```python
# command.py
from dataclasses import dataclass

from mediary.cqrs import Command, command


@command
@dataclass(frozen=True)
class WatchIssue(Command[None]):
    """Start or stop watching an issue."""

    key: str
    watch: bool = True
```

```python
# handler.py
from mediary.cqrs import command_handler

from acli_py.application.commands.watch_issue.command import WatchIssue


@command_handler
def watch_issue(command: WatchIssue, site: Site) -> None:
    """Add or remove the user as a watcher."""
```

The bus finds the handler by itself: `bootstrap.build_bus` scans `commands/`, `queries/` and
`events/`. Handlers are plain synchronous functions. mediary runs them on a worker thread,
and passes their other parameters (the dependencies) from the composition root's resolver.
Front ends then `await bus.send(WatchIssue("DEMO-1"))`. Test the handler against the fake Jira
site in `tests/fake_jira.py`.

### Adding a query

A query only reads. Its folder has a third file, `view.py`, holding the read model that front
ends display. `application/queries/get_issue/` is the worked example to copy:

```text
application/queries/get_issue/
  query.py      # GetIssue(key, fields): the question
  handler.py    # asks the IssueReader port, returns an IssueView
  view.py       # IssueView: to_rich(), to_json(), to_markdown()
```

```python
# handler.py
from mediary.cqrs import query_handler

from acli_py.application.ports import IssueReader


@query_handler
def get_issue(request: GetIssue, issues: IssueReader) -> IssueView:
    """Read the issue and wrap it in its view."""
    issue = issues.get_issue(request.key.strip().upper(), request.fields)
    return IssueView(issue, issues.browse_url(issue.key))
```

- The handler depends on a **port** (a `Protocol` in `application/ports.py`), never on the
  Jira client. The adapter lives in `infrastructure/jira/`, and `bootstrap.SiteResolver` maps
  the port to it.
- The adapter turns Jira's JSON into **domain objects** (`domain/issue.py`) once; views and
  front ends never dig through raw JSON.
- The **view** knows how to show itself, so the CLI (`print(view.to_rich())`,
  `print_json(view.to_json())`), the TUI (`view.to_markdown()`) and the shell all show the
  same thing.
- Queries are frozen dataclasses because they are the query cache's keys.
- Tests (see `tests/test_get_issue.py`): the domain parsing on plain dicts, the handler with a
  stub port and against the fake Jira, each rendering of the view, and the command end to end.

### Adding a subscriber

Events say what happened (`application/events/<event>/event.py`). Anyone who reacts to one
adds a function to that event's `subscribers.py`:

```python
from mediary.cqrs import event_handler


@event_handler
def write_audit_record(event: IssueChanged, log: AuditLog) -> None:
    """Remember the change, so it can be undone."""
```

Subscribers never call back into commands; if a reaction needs to change Jira, it belongs in
the command's handler.

## Documentation

The docs site is built with [Sphinx](https://www.sphinx-doc.org/), the
[Shibuya](https://shibuya.lepture.com/) theme and [MyST](https://myst-parser.readthedocs.io/)
Markdown from `docs/`. Preview it, rebuilt on every save, at http://127.0.0.1:8000:

```sh
uv run --isolated --python 3.13 --group docs sphinx-autobuild -b dirhtml docs docs/_build/html
```

Sphinx 9 needs Python 3.12+, hence `--python 3.13`; `--isolated` keeps it out of `.venv`.
CI builds the site with `-W`, so broken links and references fail the build.

The command reference (`docs/commands/`) is generated from the CLI's own help texts. After
changing a command, an option or a help text, run `uv run python scripts/cli_docs.py`.
`tests/test_docs.py` fails when the reference is out of date. After changing how the TUI looks,
run `uv run python scripts/tui_screenshots.py` to redraw the screenshots in `docs/_static/`.

[Read the Docs](https://app.readthedocs.org/) builds and hosts the site from
`.readthedocs.yaml`: `latest` is `main`, each release tag gets its own version, and `stable`
is the newest release. It is served at <https://docs.codeonym.work/projects/acli-py/>.

## Releases

Releases are automated with [release-please](https://github.com/googleapis/release-please). Merges
to `main` keep a `chore(main): release X.Y.Z` PR up to date; merging it tags the release, updates
`CHANGELOG.md` and publishes to PyPI through Trusted Publishing. Never edit the version by hand.

Versions follow [SemVer](https://semver.org/). Before 1.0.0, breaking changes bump the minor version.

## Reporting bugs and security issues

- Bugs and feature ideas: [open an issue](https://github.com/codeonym-oss/acli-py/issues/new/choose).
- Security vulnerabilities: see [SECURITY.md](SECURITY.md). Please don't open public issues for them.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
