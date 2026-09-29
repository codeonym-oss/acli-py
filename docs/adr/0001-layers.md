# ADR 0001: Four layers, one bus

- **Status:** accepted
- **Date:** 2026-09-30

## Context

Up to 0.2, `acli-py` grew two ways of changing Jira. The command line called the HTTP client
directly from its Typer commands, while the TUI and the shell went through a small CQRS layer
on [mediary](https://pypi.org/project/mediary/). The same change (a transition, an
assignment) was written twice, with slightly different checks and messages. Command modules
mixed four jobs: reading options, applying Jira's rules, calling the API and printing. Raw Jira
JSON travelled everywhere, so every reader had to know its shape. Confirmation, bulk runs and
dry-run reporting were helpers each command had to remember to call.

We want every front end to behave the same, confirmations and bulk runs that no command can
forget, and code a newcomer can find their way through.

## Decision

The package is split into four layers, plus one composition root:

```text
acli_py/
  domain/            Jira's concepts and rules as plain Python: no I/O, no framework
  application/       use cases as messages on one mediator, and what wraps them
    commands/<use_case>/  command.py · handler.py
    queries/<use_case>/   query.py · handler.py · view.py
    events/<event>/       event.py · subscribers.py
    behaviors/            activity, cache, announce (later: confirm, bulk, audit)
  infrastructure/    the outside world: the Jira client, config, credentials, files
  presentation/      the front ends: cli/, shell.py, tui/, and output.py
  bootstrap.py       the composition root: builds the bus and the adapters
```

### The dependency rule

Each layer imports only the layers below it:

```text
presentation → bootstrap → infrastructure → application → domain
```

- **Domain** imports nothing from the other layers.
- **Application** imports only the domain. When a handler needs the outside world, it asks for
  a port (a `Protocol`), and infrastructure implements it.
- **Infrastructure** implements the application's ports, and may use the domain to build and
  parse what Jira sends.
- **Presentation** reaches infrastructure only through `acli_py.bootstrap`. A front end asks
  the composition root for a ready bus or catalog; it never builds a client or a handler.

[import-linter](https://import-linter.readthedocs.io/) checks these rules in pre-commit and CI
(`uv run lint-imports`; the contracts are in `pyproject.toml`).

### One package per use case

A use case is a folder named after what it does, such as `transition_issue` or `get_issue`.
Its message and its handler sit side by side, and nothing else lives there:

- `command.py`: a frozen dataclass describing the change, which is also what confirmations
  and the audit log show.
- `query.py` and `view.py`: the question, and the read model front ends display (as a table,
  JSON, Markdown…). Views are built from domain objects, never from raw JSON.
- `handler.py`: a plain function from the message and its dependencies to the result.
- `events/<event>/`: what happened (`event.py`), and everyone who reacts to it
  (`subscribers.py`), such as the cache, the audit log and the TUI.

Finding the code for "assign an issue" means opening `application/commands/assign_issue/`.
Adding a use case adds a folder; it doesn't grow a thousand-line module.

### mediary is the only way to reach Jira

Every front end, the command line included, sends messages through the same bus
(`acli_py.application.bus.Bus`, built by `acli_py.bootstrap.build_bus`). Behaviors wrap every
message, so cross-cutting rules live in one place: activity tracking, caching, events after a
change, and soon confirmation, bulk runs and the audit log. A new command gets them all by
being a command.

## Where the existing modules went

| Module | Layer | Why |
|---|---|---|
| `domain/adf.py` | domain | Markdown ⇄ Jira's document format is a pure conversion |
| `domain/jql/` | domain | The query language: lexer, smart queries, completion, and the `Catalog` port |
| `infrastructure/jira/client.py` | infrastructure | HTTP, retries, dry-run planning |
| `infrastructure/jira/catalog.py` | infrastructure | `JiraCatalog`, the `Catalog` port backed by Jira |
| `infrastructure/jira/resolve.py`, `fields.py` | infrastructure | They look names up through the API and build its payloads |
| `infrastructure/config.py`, `credentials.py`, `storage.py` | infrastructure | Files and the OS keyring |
| `application/bus.py`, `behaviors/` | application | The mediator and what wraps every message |
| `application/messages.py`, `handlers.py`, `site.py` | application | The use cases written before this layout |
| `presentation/cli/`, `shell.py`, `tui/`, `output.py` | presentation | The front ends |

## Consequences

- The move is **expand–contract**. The layers exist now, and code written before them is
  allowed to break the rules through the explicit `ignore_imports` lists in `pyproject.toml`.
  Each use case that moves into its own package deletes its lines there, and import-linter
  fails on a line that no longer matches, so the list only shrinks. When it is empty, the
  migration is done (issue #18).
- `application/messages.py` and `handlers.py` shrink as their use cases move into
  `commands/` and `queries/`, then disappear.
- Handlers still reach the client through `Site`. The first tracer bullets (issues #9 and #10)
  replace that with ports, so the application layer stops importing infrastructure.
- Tests follow the layers: domain tests need nothing; handler tests run against the fake Jira
  site; front-end tests drive the CLI, the shell or the TUI end to end.
