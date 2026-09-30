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
    behaviors/            activity, cache, confirm, announce
    bulk.py · audit.py    the bulk engine, and the audit trail (one record per run)
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

### Ports and adapters

A handler that needs the outside world names a port, a `Protocol` in
`acli_py.application.ports` (such as `IssueReader`). Infrastructure implements it (such as
`acli_py.infrastructure.jira.issues.JiraIssues`), and the composition root's resolver hands the
adapter to the handler. Adapters return domain objects, parsed from Jira's JSON once, so
nothing above them digs through raw dicts.

### The worked example: `get_issue`

`application/queries/get_issue/` is the first use case built this way, and the one to copy:

1. `domain/issue.py`: `Issue` and its value objects (`Status`, `User`, `IssueRef`, `Link`…),
   with `Issue.from_jira`.
2. `application/ports.py`: `IssueReader.get_issue(key, fields) -> Issue`.
3. `infrastructure/jira/issues.py`: `JiraIssues`, the adapter over the REST client.
4. `application/queries/get_issue/`: `GetIssue` (query), `get_issue` (handler) and
   `IssueView` (view), which renders as a Rich panel, JSON or Markdown.
5. Front ends send the query: `acli-py issue view` (and so the shell) prints
   `view.to_rich()` or `view.to_json()`; the TUI's detail pane shows `view.to_markdown()`.
6. `tests/test_get_issue.py` tests each layer; `tests/test_issue.py` runs the command.

`application/commands/transition_issue/` is the one to copy for a command:

1. `domain/workflow.py`: `Transition`, and `pick`, which finds the transition a user means
   by id, target status or name.
2. `application/ports.py`: `Workflow` (status, transitions, transition).
3. `infrastructure/jira/workflow.py`: `JiraWorkflow`, the adapter.
4. `application/commands/transition_issue/`: `TransitionIssue` declares its `Change`
   ("Move DEMO-1 to Done"); its handler returns what `Changed` (the status before and after).
5. `application/events/issue_changed/`: `IssueChanged` carries the before and after; its
   subscribers drop the query cache, append to the audit log and tell the TUI.
6. Front ends provide the `Confirmer` port: a y/N question on the CLI and in the shell, a
   modal in the TUI.

### Asking before a change

Every command that changes Jira has a `change()` method returning a `Change` (the `Write`
protocol in `application/changes.py`). The `Confirm` behavior shows it and runs the command
only if the user agrees. It never asks in a dry run or with `--yes`. With no terminal to ask
on, the CLI refuses unless given `--yes`. A front end running one change over many issues
approves the whole change first (`bus.confirm.approve` or `batch`), so the user is asked once,
not once per issue.

### The bulk engine

`application/bulk.py` runs one kind of command over many issues, for every front end
(`bus.bulk.run(commands)`). It refuses more than `SAFETY_CAP` issues unless forced, asks once
about the change the commands make together, with a preview of each issue's value now and
after (from commands that are `Previewable`, fetched in one search), runs them a few at a time
and reports each `Outcome` as it lands. After a failure it starts no new commands unless told
to keep going. Its `Report` says what worked, what failed and what was never tried.

### The audit log

Each run of a command that was not a dry run is appended to `audit.jsonl` in the config
directory, one JSON object per line: `at`, `command`, `keys`, `changes` (each issue's `key`,
`before` and `after`) and `failed` (issue → why). The `issue_changed` subscriber notes each
change in the `AuditTrail`; a command on its own is recorded at once, while a bulk run
gathers its changes and is recorded once at the end. Undo (#19) reads it back. A log that
cannot be written never fails the change it records.

### mediary is the only way to reach Jira

Every front end, the command line included, sends messages through the same bus
(`acli_py.application.bus.Bus`, built by `acli_py.bootstrap.build_bus`). Behaviors wrap every
message, so cross-cutting rules live in one place: activity tracking, caching, confirmation,
events after a change, the audit log and bulk runs. A new command gets them all by
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
| `application/ports.py` | application | What use cases need from outside, as protocols |
| `domain/issue.py`, `domain/values.py` | domain | An issue as typed objects; how Jira's values read |
| `infrastructure/jira/issues.py` | infrastructure | `JiraIssues`, the `IssueReader` port over the client |
| `domain/workflow.py`, `infrastructure/jira/workflow.py` | domain, infrastructure | Transitions, and `JiraWorkflow`, the `Workflow` port |
| `application/changes.py` | application | `Change`, `Changed`, `Declined`: what commands change |
| `application/bulk.py`, `audit.py` | application | The bulk engine; the audit trail, one record per run |
| `infrastructure/audit.py` | infrastructure | `AuditFile`, the `AuditLog` port as JSON lines |
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
- The handlers in `application/handlers.py` still reach the client through `Site`. Each one
  that moves to its own package asks for a port instead; when the last one moves, `Site`
  leaves the application layer and the layers contract has no exceptions left.
- Tests follow the layers: domain tests need nothing; handler tests run against the fake Jira
  site; front-end tests drive the CLI, the shell or the TUI end to end.
