# acli-py

[![CI](https://github.com/codeonym-oss/acli-py/actions/workflows/ci.yml/badge.svg)](https://github.com/codeonym-oss/acli-py/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/codeonym-oss/acli-py/blob/main/LICENSE)

`aj` is a friendly command line for **Jira Cloud**. It is a Python port of the Jira side of
Atlassian's [`acli`](https://developer.atlassian.com/cloud/acli/), redesigned around short,
predictable commands and a **dry-run mode for every change**.

```sh
aj issue create -p DEMO -t Bug -s "Login fails on Safari" -a @me -L web
aj issue transition DEMO-12 --to "In Progress" -m "On it"
aj issue edit --jql 'project = DEMO AND labels = legacy' --remove-label legacy --dry-run
aj sprint start 42 --weeks 2
```

- **Every Jira object you work with daily:** issues (create, view, search, edit, assign,
  transition, clone, archive, delete), comments, links, attachments, watchers, worklogs,
  projects, boards, sprints, filters, custom fields, dashboards and users. There is also
  `aj api` for any other endpoint.
- **Dry run everywhere.** Add `--dry-run` (`-n`) to any command, or put it in front
  (`aj -n …`), or set `ACLI_PY_DRY_RUN=1`. Reads still happen, so targets are resolved for
  real, but each write is printed instead of sent. The HTTP client enforces this, so no
  command can skip it.
- **Bulk by default.** Commands that change issues take keys (`DEMO-1 DEMO-2`), `--jql`,
  `--filter` or `--from-file`. They ask before touching more than one issue, report ✔/✘ per
  issue, and stop at the first failure unless you pass `--ignore-errors`.
- **Human input.** Say `@me`, an email or part of a name instead of account ids.
  Descriptions and comments are Markdown, converted to Jira's rich-text format. Any field is
  settable by name: `-F "Story point estimate=5"`, `-F "Team=Blue"`, or raw JSON with
  `-F 'Team:={"id": "10042"}'`.
- **Script-friendly.** Lists print a table, `--json` or `--csv`. Results go to stdout and
  messages to stderr. Prompts refuse to guess without a terminal (pass `--yes`).
- **Several accounts.** Log in to as many sites as you like and switch between them. API
  tokens live in the system keyring, or in an owner-only file when there is no keyring.

## Install

It needs Python 3.10 or newer, on Linux, macOS or Windows. Until the first PyPI release,
install it from the repository with [uv](https://docs.astral.sh/uv/) or
[pipx](https://pipx.pypa.io/):

```sh
uv tool install git+https://github.com/codeonym-oss/acli-py   # or: pipx install git+…
aj --version
```

That installs two identical commands: `aj`, and `acli-py` for when `aj` is taken.

## Getting started

```sh
aj auth login                  # site, email and an API token (typed hidden)
aj config set project DEMO     # optional: the project used when -p is left out
aj issue search -a @me --open  # my unfinished issues
```

Create an API token at <https://id.atlassian.com/manage-profile/security/api-tokens>. For
scripts, `echo "$TOKEN" | aj auth login -s team.atlassian.net -e me@example.com --token-stdin`.
In CI, skip the login and set `ACLI_PY_SITE`, `ACLI_PY_EMAIL` and `ACLI_PY_API_TOKEN`.

## Commands

Every command has `--help` with examples. The whole tree:

| Command | What it does |
|---|---|
| `aj auth login \| logout \| status \| switch` | Manage accounts. `status --check` verifies the token. |
| `aj config show \| set \| unset \| path` | Defaults: `project`, `issue-type`, `board`, `editor`. |
| `aj issue view KEY` | Details, description (rendered Markdown), subtasks, links, attachments, latest comments. `--web`, `--json`. |
| `aj issue search [JQL]` | Search with JQL and/or `-p -a -s -t -L --text --open --filter --order`. `--count`, `--all`, `--fields`, `--csv`, `--web`. Alias `list`. |
| `aj issue create` | One issue from options or `--editor`, or many from `--from-json` / `--from-csv` (`--template` prints an example). |
| `aj issue edit KEYS…` | Summary, description, type, priority, labels (`--add-label`, `--remove-label`), components, versions, parent, due date, any `-F` field. |
| `aj issue assign KEYS… --to USER` | Assign to `@me`, a person, `default`, or `--unassign`. |
| `aj issue transition KEYS… --to STATUS` | Move by status or transition name, with `-m` comment, `--resolution` and fields. Alias `move`. `transitions KEY` lists options. |
| `aj issue clone KEYS…` | Copy issues, in place or `--to-project`, linked to the original. |
| `aj issue archive \| unarchive \| delete KEYS…` | Archive, restore, or permanently delete (`--with-subtasks`). |
| `aj issue open KEY` | Open in the browser. |
| `aj issue comment list \| add \| edit \| delete \| visibility` | Markdown comments. Role/group visibility, `--edit-last`, `--editor`, stdin. |
| `aj issue link add A blocks B \| list \| delete \| types` | Links read as a sentence, with inward phrases too (`"is blocked by"`). Bulk from JSON/CSV. |
| `aj issue attachment list \| upload \| download \| delete` | Files on an issue. |
| `aj issue watcher list \| add \| remove` | Watchers (yourself by default). |
| `aj issue worklog list \| add \| delete` | Log time: `aj issue worklog add DEMO-1 "1h 30m" -m "Pairing"`. |
| `aj project list \| view \| create \| update \| archive \| restore \| delete` | Projects. `create -T scrum\|kanban\|basic\|tasks\|process\|service`. `components`, `versions`. |
| `aj board list \| view \| create \| delete \| projects \| sprints \| backlog` | Boards. |
| `aj sprint list \| view \| issues \| create \| update \| start \| close \| delete \| add \| remove` | Sprints, and moving issues in and out of them. |
| `aj filter list \| search \| view \| create \| update \| delete \| star \| owner \| columns` | Saved filters, sharing, favourites, navigator columns. |
| `aj field list \| create \| update \| delete \| restore` | Fields and their ids. `create --type text\|number\|select\|date\|user…`. |
| `aj dashboard list \| view` | Dashboards. |
| `aj user search \| view` | Look people up (`aj user view` is you). |
| `aj meta statuses \| priorities \| resolutions \| issue-types` | Site-wide lists. |
| `aj api METHOD PATH` | Any REST endpoint with your credentials: `aj api GET myself`, `-d @body.json`, `-q key=value`. |

Global options go before the command: `--dry-run`, `--account EMAIL@SITE` (use another saved
account once), and `--debug` (trace every HTTP request).

## Dry run

```console
$ aj issue link add DEMO-2 "is blocked by" DEMO-3 --dry-run
╭─ DRY RUN POST /rest/api/3/issueLink ─╮
│ {                                    │
│   "type": {                          │
│     "name": "Blocks"                 │
│   },                                 │
│   "outwardIssue": {                  │
│     "key": "DEMO-3"                  │
│   },                                 │
│   "inwardIssue": {                   │
│     "key": "DEMO-2"                  │
│   }                                  │
│ }                                    │
╰──────────────────────────────────────╯
✔ DEMO-2 is blocked by DEMO-3 would be linked
DRY RUN 1 change planned, nothing was sent to Jira.
```

Rich text in a plan is shown as the Markdown you typed (`"ADF: …"`), not as raw ADF JSON.
Confirmation prompts are skipped during a dry run, because nothing will change.

## Coming from `acli`

| acli | aj |
|---|---|
| `acli jira auth login --site S --email E --token < t` | `aj auth login -s S -e E --token-stdin < t` |
| `acli jira workitem view KEY-1` | `aj issue view KEY-1` |
| `acli jira workitem search --jql "…" --paginate` | `aj issue search "…" --all` |
| `acli jira workitem create --summary S --project P --type T` | `aj issue create -s S -p P -t T` |
| `acli jira workitem create-bulk --from-csv f.csv` | `aj issue create --from-csv f.csv` |
| `acli jira workitem edit --key K --summary S` | `aj issue edit K -s S` |
| `acli jira workitem transition --key K --status Done` | `aj issue transition K --to Done` |
| `acli jira workitem assign --key K --assignee @me` | `aj issue assign K --to @me` |
| `acli jira workitem comment create --key K --body B` | `aj issue comment add K -b B` |
| `acli jira workitem link create --out A --in B --type Blocks` | `aj issue link add A blocks B` |
| `acli jira workitem list-watchers --key K` | `aj issue watcher list K` |
| `acli jira project create --key K --name N` | `aj project create -k K --name N` |
| `acli jira board list-sprints --id 1` | `aj board sprints 1` or `aj sprint list 1` |
| `acli jira sprint list-workitems --sprint 7 --board 1` | `aj sprint issues 7` |
| `acli jira filter add-favourite --filter-id 1` | `aj filter star 1` |
| `acli jira field delete --id customfield_1` | `aj field delete customfield_1` |
| `acli jira dashboard search` | `aj dashboard list` |

`aj workitem …` is a hidden alias of `aj issue …`. Not ported: OAuth browser login
(`--web`), which needs an Atlassian OAuth app, and acli's Confluence, admin and Rovo Dev
commands.

## Configuration

| | |
|---|---|
| Config file | `aj config path`. `ACLI_PY_CONFIG_DIR` moves it. Never holds tokens. |
| Tokens | System keyring, or `credentials.json` (0600) next to the config. Force one with `ACLI_PY_CREDENTIAL_BACKEND=keyring\|file`. |
| `ACLI_PY_API_TOKEN` | Used instead of the stored token, never saved. |
| `ACLI_PY_SITE`, `ACLI_PY_EMAIL` | With `ACLI_PY_API_TOKEN`: run without logging in (CI). |
| `ACLI_PY_DRY_RUN=1` | Every command is a dry run. |
| `VISUAL` / `EDITOR` | Used by `--editor` (or `aj config set editor "code --wait"`). |

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: `uv sync`, then `uv run pytest`. The
tests run the real CLI over real HTTP against `tests/fake_jira.py`, a stateful in-memory
Jira. A parametrised test checks that every write command sends nothing under `--dry-run`.

## License

MIT
