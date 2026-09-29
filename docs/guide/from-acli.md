# Coming from acli

`acli-py` covers every Jira command of Atlassian's `acli`, with a flatter layout: nouns first, keys
as arguments, and the same options across commands. The table below was checked against
**acli 1.3.39-stable**, command by command and flag by flag; a test keeps every `acli-py` command in
it real.

`acli-py workitem …` also works, as a hidden alias of `acli-py issue …`.

## Work items

| acli | acli-py |
|---|---|
| `acli jira workitem view KEY-1 --fields F --web` | `acli-py issue view KEY-1 --fields F --web` |
| `acli jira workitem search --jql "…" --paginate` | `acli-py issue search "…" --all` |
| `acli jira workitem search --jql "…" --count` / `--csv` / `--web` | `acli-py issue search "…" --count` / `--csv` / `--web` |
| `acli jira workitem search --filter 10001` | `acli-py issue search --filter 10001` |
| `acli jira workitem create --summary S --project P --type T` | `acli-py issue create -s S -p P -t T` |
| `acli jira workitem create --from-file f.txt` | `acli-py issue create --from-file f.txt` |
| `acli jira workitem create --generate-json` | `acli-py issue create --template` |
| `acli jira workitem create --from-json f.json` | `acli-py issue create --from-json f.json` |
| `acli jira workitem create-bulk --from-csv f.csv` / `--from-json` | `acli-py issue create --from-csv f.csv` / `--from-json` |
| `acli jira workitem edit --key K --summary S` | `acli-py issue edit K -s S` |
| `acli jira workitem edit --jql Q --labels L --remove-labels M` | `acli-py issue edit --jql Q --add-label L --remove-label M` |
| `acli jira workitem edit --generate-json` / `--from-json` | `acli-py issue edit --template` / `--from-json` |
| `acli jira workitem edit --key K --remove-assignee` | `acli-py issue edit K -a none` |
| `acli jira workitem transition --key K --status Done` | `acli-py issue transition K --to Done` |
| `acli jira workitem assign --key K --assignee @me` | `acli-py issue assign K --to @me` |
| `acli jira workitem assign --key K --remove-assignee` | `acli-py issue assign K --unassign` |
| `acli jira workitem clone --key K --to-project P` | `acli-py issue clone K --to-project P` |
| `acli jira workitem clone --key K --to-site S` | `acli-py issue clone K --to-site S --to-project P` |
| `acli jira workitem archive` / `unarchive` / `delete --key K` | `acli-py issue archive` / `unarchive` / `delete K` |
| `acli jira workitem comment create --key K --body B` | `acli-py issue comment add K -b B` |
| `acli jira workitem comment create --jql Q --body-file F` | `acli-py issue comment add --jql Q -B F` |
| `acli jira workitem comment create --key K --edit-last` | `acli-py issue comment add K --edit-last` |
| `acli jira workitem comment list --key K --order -created` | `acli-py issue comment list K --newest-first` |
| `acli jira workitem comment update --key K --id I --body B` | `acli-py issue comment edit K I -b B` |
| `acli jira workitem comment update --key K --id I --body-adf F` | `acli-py issue comment edit K I --body-adf F` |
| `acli jira workitem comment delete --key K --id I` | `acli-py issue comment delete K I` |
| `acli jira workitem comment visibility --role --project P` | `acli-py issue comment visibility -p P` |
| `acli jira workitem link create --out A --in B --type Blocks` | `acli-py issue link add A blocks B` |
| `acli jira workitem link create --generate-json` / `--from-json` | `acli-py issue link add --template` / `--from-json` |
| `acli jira workitem link delete --id I` | `acli-py issue link delete I` |
| `acli jira workitem link list --key K` / `link type` | `acli-py issue link list K` / `acli-py issue link types` |
| `acli jira workitem attachment list --key K` / `delete --id I` | `acli-py issue attachment list K` / `delete I` |
| `acli jira workitem list-watchers --key K` (and `watcher list`) | `acli-py issue watcher list K` |
| `acli jira workitem watcher remove --key K --user U` | `acli-py issue watcher remove K U` |

## Projects, boards and sprints

| acli | acli-py |
|---|---|
| `acli jira project list --recent` / `--paginate` | `acli-py project list --recent` / `--all` |
| `acli jira project view --key K` | `acli-py project view K` |
| `acli jira project create --key K --name N` | `acli-py project create -k K --name N` |
| `acli jira project create --from-project T --key K --name N` | `acli-py project create --from-project T -k K --name N` |
| `acli jira project create --generate-json` / `--from-json` | `acli-py project create --print-template` / `--from-json` |
| `acli jira project update --project-key K --name N` | `acli-py project update K --name N` |
| `acli jira project archive` / `restore` / `delete --key K` | `acli-py project archive` / `restore` / `delete K` |
| `acli jira board search --project P --order-by -name` | `acli-py board list -p P --order -name` |
| `acli jira board search --private` | `acli-py board list --private` |
| `acli jira board get --id 1` / `board view --id 1` | `acli-py board view 1` |
| `acli jira board create --name N --type scrum --filter-id F` | `acli-py board create --name N --type scrum --filter F` |
| `acli jira board delete --id 1` | `acli-py board delete 1` |
| `acli jira board list-projects --id 1` | `acli-py board projects 1` |
| `acli jira board list-sprints --id 1 --state active` | `acli-py sprint list 1 -s active` |
| `acli jira sprint view --id 7` | `acli-py sprint view 7` |
| `acli jira sprint create --name N --board 1` | `acli-py sprint create --name N -b 1` |
| `acli jira sprint update --id 7 --name N --goal G` | `acli-py sprint update 7 --name N --goal G` |
| `acli jira sprint update --id 7 --state active` / `closed` | `acli-py sprint start 7` / `acli-py sprint close 7` |
| `acli jira sprint delete --id 7` | `acli-py sprint delete 7` |
| `acli jira sprint list-workitems --sprint 7 --board 1` | `acli-py sprint issues 7` |

## Filters, fields and dashboards

| acli | acli-py |
|---|---|
| `acli jira filter list --my` / `--favourite` | `acli-py filter list` / `--favourites` |
| `acli jira filter search --name N --owner O` | `acli-py filter search --name N --owner O` |
| `acli jira filter get --id 1` / `view --id 1` | `acli-py filter view 1` |
| `acli jira filter update --id 1 --jql Q` | `acli-py filter update 1 --jql Q` |
| `acli jira filter add-favourite --filter-id 1` | `acli-py filter star 1` |
| `acli jira filter change-owner --id 1 --owner E` | `acli-py filter owner 1 --to E` |
| `acli jira filter change-owner --from-file F --owner E` | `acli-py filter owner --from-file F --to E` |
| `acli jira filter get-columns` / `list-columns --key 1` | `acli-py filter columns 1` |
| `acli jira filter reset-columns --id 1` | `acli-py filter columns 1 --reset` |
| `acli jira field create --name N --type T` | `acli-py field create --name N -t number` |
| `acli jira field update --id F --name N` | `acli-py field update F --name N` |
| `acli jira field delete --id F` | `acli-py field delete F` |
| `acli jira field restore` / `cancel-delete --id F` | `acli-py field restore F` |
| `acli jira dashboard search --name N --owner O` | `acli-py dashboard list --name N --owner O` |

## Accounts

| acli | acli-py |
|---|---|
| `acli jira auth login --site S --email E --token < t` | `acli-py auth login -s S -e E --token-stdin < t` |
| `acli jira auth status` / `switch` / `logout` | `acli-py auth status` / `switch` / `logout` |

## What's new in acli-py

- **An interactive side:** `acli-py tui`, a full-screen issue browser, and `acli-py shell`, a prompt
  that completes commands and your site's values. See [Interactive](interactive.md).
- **Smart queries** anywhere a search goes: `acli-py issue search '@me is:open #web sort:-priority'`.
  JQL still works, with completion in the TUI and the shell.
- `--dry-run` on every change, plus `acli-py -n …` and `ACLI_PY_DRY_RUN=1`.
- `acli-py issue transitions`, `open`, and worklogs (`acli-py issue worklog`).
- Attachment upload and download, and watcher add.
- `acli-py sprint start`, `close`, `add`, `remove`, and `acli-py board backlog`.
- `acli-py filter create`, `delete`, `star --remove`, `columns --set`.
- `acli-py field list`, `acli-py user search/view`, `acli-py meta …`, `acli-py project components/versions`.
- `acli-py api` for any REST endpoint.
- `-F NAME=VALUE` for any field, and Markdown for rich text.

## Not ported

- OAuth browser login (`auth login --web`), which needs a registered Atlassian OAuth app.
  API tokens do the same job.
- acli's Confluence, admin, Guard and Rovo Dev commands.
