# Coming from acli

`aj` covers the Jira commands of Atlassian's `acli`, with a flatter layout: nouns first, keys
as arguments, and the same options across commands.

| acli | aj |
|---|---|
| `acli jira auth login --site S --email E --token < t` | `aj auth login -s S -e E --token-stdin < t` |
| `acli jira auth status` / `switch` / `logout` | `aj auth status` / `switch` / `logout` |
| `acli jira workitem view KEY-1` | `aj issue view KEY-1` |
| `acli jira workitem search --jql "…" --paginate` | `aj issue search "…" --all` |
| `acli jira workitem search --jql "…" --count` | `aj issue search "…" --count` |
| `acli jira workitem create --summary S --project P --type T` | `aj issue create -s S -p P -t T` |
| `acli jira workitem create --generate-json` | `aj issue create --template` |
| `acli jira workitem create-bulk --from-csv f.csv` | `aj issue create --from-csv f.csv` |
| `acli jira workitem edit --key K --summary S` | `aj issue edit K -s S` |
| `acli jira workitem edit --jql Q --labels L` | `aj issue edit --jql Q -L L` |
| `acli jira workitem transition --key K --status Done` | `aj issue transition K --to Done` |
| `acli jira workitem assign --key K --assignee @me` | `aj issue assign K --to @me` |
| `acli jira workitem assign --key K --remove-assignee` | `aj issue assign K --unassign` |
| `acli jira workitem clone --key K --to-project P` | `aj issue clone K --to-project P` |
| `acli jira workitem archive` / `unarchive` / `delete` | `aj issue archive` / `unarchive` / `delete` |
| `acli jira workitem comment create --key K --body B` | `aj issue comment add K -b B` |
| `acli jira workitem comment list --key K` | `aj issue comment list K` |
| `acli jira workitem comment update --key K --id I --body B` | `aj issue comment edit K I -b B` |
| `acli jira workitem comment delete --key K --id I` | `aj issue comment delete K I` |
| `acli jira workitem comment visibility --role --project P` | `aj issue comment visibility -p P` |
| `acli jira workitem link create --out A --in B --type Blocks` | `aj issue link add A blocks B` |
| `acli jira workitem link list --key K` / `type` | `aj issue link list K` / `aj issue link types` |
| `acli jira workitem attachment list --key K` | `aj issue attachment list K` |
| `acli jira workitem list-watchers --key K` | `aj issue watcher list K` |
| `acli jira workitem watcher remove --key K --user U` | `aj issue watcher remove K U` |
| `acli jira project list --recent` | `aj project list --recent` |
| `acli jira project create --key K --name N` | `aj project create -k K --name N` |
| `acli jira project update --project-key K --name N` | `aj project update K --name N` |
| `acli jira project archive` / `restore` / `delete --key K` | `aj project archive` / `restore` / `delete K` |
| `acli jira board search --project P` | `aj board list -p P` |
| `acli jira board view --id 1` | `aj board view 1` |
| `acli jira board list-projects --id 1` | `aj board projects 1` |
| `acli jira board list-sprints --id 1 --state active` | `aj sprint list 1 -s active` |
| `acli jira sprint create --name N --board 1` | `aj sprint create --name N -b 1` |
| `acli jira sprint update --id 7 --state closed` | `aj sprint close 7` |
| `acli jira sprint list-workitems --sprint 7 --board 1` | `aj sprint issues 7` |
| `acli jira filter list --my` / `--favourite` | `aj filter list` / `--favourites` |
| `acli jira filter add-favourite --filter-id 1` | `aj filter star 1` |
| `acli jira filter change-owner --id 1 --owner E` | `aj filter owner 1 --to E` |
| `acli jira filter list-columns --key 1` / `reset-columns` | `aj filter columns 1` / `--reset` |
| `acli jira field create --name N --type T` | `aj field create --name N -t number` |
| `acli jira field delete` / `restore --id F` | `aj field delete` / `restore F` |
| `acli jira dashboard search --name N` | `aj dashboard list -q N` |

## What's new in aj

- `--dry-run` on every change, plus `aj -n …` and `ACLI_PY_DRY_RUN=1`
- `aj issue transitions`, `open`, and worklogs (`aj issue worklog`)
- attachment upload and download, and watcher add
- `aj sprint start`, `close`, `add`, `remove`, and `aj board backlog`
- `aj filter create`, `delete`, `star --remove`, `columns --set`
- `aj field list`, `aj user search/view`, `aj meta …`, `aj project components/versions`
- `aj api` for any REST endpoint
- `-F NAME=VALUE` for any field, and Markdown for rich text

## Not ported

- OAuth browser login (`--web`), which needs a registered Atlassian OAuth app.
  API tokens do the same job.
- Cloning to another site (`--to-site`).
- acli's Confluence, admin, Guard and Rovo Dev commands.
