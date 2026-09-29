# Coming from acli

`aj` covers every Jira command of Atlassian's `acli`, with a flatter layout: nouns first, keys
as arguments, and the same options across commands. The table below was checked against
**acli 1.3.39-stable**, command by command and flag by flag; a test keeps every `aj` command in
it real.

`aj workitem …` also works, as a hidden alias of `aj issue …`.

## Work items

| acli | aj |
|---|---|
| `acli jira workitem view KEY-1 --fields F --web` | `aj issue view KEY-1 --fields F --web` |
| `acli jira workitem search --jql "…" --paginate` | `aj issue search "…" --all` |
| `acli jira workitem search --jql "…" --count` / `--csv` / `--web` | `aj issue search "…" --count` / `--csv` / `--web` |
| `acli jira workitem search --filter 10001` | `aj issue search --filter 10001` |
| `acli jira workitem create --summary S --project P --type T` | `aj issue create -s S -p P -t T` |
| `acli jira workitem create --from-file f.txt` | `aj issue create --from-file f.txt` |
| `acli jira workitem create --generate-json` | `aj issue create --template` |
| `acli jira workitem create --from-json f.json` | `aj issue create --from-json f.json` |
| `acli jira workitem create-bulk --from-csv f.csv` / `--from-json` | `aj issue create --from-csv f.csv` / `--from-json` |
| `acli jira workitem edit --key K --summary S` | `aj issue edit K -s S` |
| `acli jira workitem edit --jql Q --labels L --remove-labels M` | `aj issue edit --jql Q --add-label L --remove-label M` |
| `acli jira workitem edit --generate-json` / `--from-json` | `aj issue edit --template` / `--from-json` |
| `acli jira workitem edit --key K --remove-assignee` | `aj issue edit K -a none` |
| `acli jira workitem transition --key K --status Done` | `aj issue transition K --to Done` |
| `acli jira workitem assign --key K --assignee @me` | `aj issue assign K --to @me` |
| `acli jira workitem assign --key K --remove-assignee` | `aj issue assign K --unassign` |
| `acli jira workitem clone --key K --to-project P` | `aj issue clone K --to-project P` |
| `acli jira workitem clone --key K --to-site S` | `aj issue clone K --to-site S --to-project P` |
| `acli jira workitem archive` / `unarchive` / `delete --key K` | `aj issue archive` / `unarchive` / `delete K` |
| `acli jira workitem comment create --key K --body B` | `aj issue comment add K -b B` |
| `acli jira workitem comment create --jql Q --body-file F` | `aj issue comment add --jql Q -B F` |
| `acli jira workitem comment create --key K --edit-last` | `aj issue comment add K --edit-last` |
| `acli jira workitem comment list --key K --order -created` | `aj issue comment list K --newest-first` |
| `acli jira workitem comment update --key K --id I --body B` | `aj issue comment edit K I -b B` |
| `acli jira workitem comment update --key K --id I --body-adf F` | `aj issue comment edit K I --body-adf F` |
| `acli jira workitem comment delete --key K --id I` | `aj issue comment delete K I` |
| `acli jira workitem comment visibility --role --project P` | `aj issue comment visibility -p P` |
| `acli jira workitem link create --out A --in B --type Blocks` | `aj issue link add A blocks B` |
| `acli jira workitem link create --generate-json` / `--from-json` | `aj issue link add --template` / `--from-json` |
| `acli jira workitem link delete --id I` | `aj issue link delete I` |
| `acli jira workitem link list --key K` / `link type` | `aj issue link list K` / `aj issue link types` |
| `acli jira workitem attachment list --key K` / `delete --id I` | `aj issue attachment list K` / `delete I` |
| `acli jira workitem list-watchers --key K` (and `watcher list`) | `aj issue watcher list K` |
| `acli jira workitem watcher remove --key K --user U` | `aj issue watcher remove K U` |

## Projects, boards and sprints

| acli | aj |
|---|---|
| `acli jira project list --recent` / `--paginate` | `aj project list --recent` / `--all` |
| `acli jira project view --key K` | `aj project view K` |
| `acli jira project create --key K --name N` | `aj project create -k K --name N` |
| `acli jira project create --from-project T --key K --name N` | `aj project create --from-project T -k K --name N` |
| `acli jira project create --generate-json` / `--from-json` | `aj project create --print-template` / `--from-json` |
| `acli jira project update --project-key K --name N` | `aj project update K --name N` |
| `acli jira project archive` / `restore` / `delete --key K` | `aj project archive` / `restore` / `delete K` |
| `acli jira board search --project P --order-by -name` | `aj board list -p P --order -name` |
| `acli jira board search --private` | `aj board list --private` |
| `acli jira board get --id 1` / `board view --id 1` | `aj board view 1` |
| `acli jira board create --name N --type scrum --filter-id F` | `aj board create --name N --type scrum --filter F` |
| `acli jira board delete --id 1` | `aj board delete 1` |
| `acli jira board list-projects --id 1` | `aj board projects 1` |
| `acli jira board list-sprints --id 1 --state active` | `aj sprint list 1 -s active` |
| `acli jira sprint view --id 7` | `aj sprint view 7` |
| `acli jira sprint create --name N --board 1` | `aj sprint create --name N -b 1` |
| `acli jira sprint update --id 7 --name N --goal G` | `aj sprint update 7 --name N --goal G` |
| `acli jira sprint update --id 7 --state active` / `closed` | `aj sprint start 7` / `aj sprint close 7` |
| `acli jira sprint delete --id 7` | `aj sprint delete 7` |
| `acli jira sprint list-workitems --sprint 7 --board 1` | `aj sprint issues 7` |

## Filters, fields and dashboards

| acli | aj |
|---|---|
| `acli jira filter list --my` / `--favourite` | `aj filter list` / `--favourites` |
| `acli jira filter search --name N --owner O` | `aj filter search --name N --owner O` |
| `acli jira filter get --id 1` / `view --id 1` | `aj filter view 1` |
| `acli jira filter update --id 1 --jql Q` | `aj filter update 1 --jql Q` |
| `acli jira filter add-favourite --filter-id 1` | `aj filter star 1` |
| `acli jira filter change-owner --id 1 --owner E` | `aj filter owner 1 --to E` |
| `acli jira filter change-owner --from-file F --owner E` | `aj filter owner --from-file F --to E` |
| `acli jira filter get-columns` / `list-columns --key 1` | `aj filter columns 1` |
| `acli jira filter reset-columns --id 1` | `aj filter columns 1 --reset` |
| `acli jira field create --name N --type T` | `aj field create --name N -t number` |
| `acli jira field update --id F --name N` | `aj field update F --name N` |
| `acli jira field delete --id F` | `aj field delete F` |
| `acli jira field restore` / `cancel-delete --id F` | `aj field restore F` |
| `acli jira dashboard search --name N --owner O` | `aj dashboard list --name N --owner O` |

## Accounts

| acli | aj |
|---|---|
| `acli jira auth login --site S --email E --token < t` | `aj auth login -s S -e E --token-stdin < t` |
| `acli jira auth status` / `switch` / `logout` | `aj auth status` / `switch` / `logout` |

## What's new in aj

- **An interactive side:** `aj tui`, a full-screen issue browser, and `aj shell`, a prompt
  that completes commands and your site's values. See [Interactive](interactive.md).
- **Smart queries** anywhere a search goes: `aj issue search '@me is:open #web sort:-priority'`.
  JQL still works, with completion in the TUI and the shell.
- `--dry-run` on every change, plus `aj -n …` and `ACLI_PY_DRY_RUN=1`.
- `aj issue transitions`, `open`, and worklogs (`aj issue worklog`).
- Attachment upload and download, and watcher add.
- `aj sprint start`, `close`, `add`, `remove`, and `aj board backlog`.
- `aj filter create`, `delete`, `star --remove`, `columns --set`.
- `aj field list`, `aj user search/view`, `aj meta …`, `aj project components/versions`.
- `aj api` for any REST endpoint.
- `-F NAME=VALUE` for any field, and Markdown for rich text.

## Not ported

- OAuth browser login (`auth login --web`), which needs a registered Atlassian OAuth app.
  API tokens do the same job.
- acli's Confluence, admin, Guard and Rovo Dev commands.
