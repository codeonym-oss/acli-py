# Fields and rich text

## Any field, by name

`acli-py issue create` and `acli-py issue edit` have options for the common fields. `-F`/`--field` sets
any other field by its name or id, and converts the value to what the field expects:

```sh
acli-py issue edit DEMO-3 -F "Story point estimate=5"   # number
acli-py issue edit DEMO-3 -F "Team=Blue"                # single select
acli-py issue edit DEMO-3 -F "Region=Europe > Paris"    # cascading select
acli-py issue edit DEMO-3 -F "Reviewers=@me,bob@example.com"  # multi-user picker
acli-py issue edit DEMO-3 -F "Notes=Needs a **second** look"  # multi-line text (Markdown)
acli-py issue edit DEMO-3 -F 'customfield_10042:={"id": "10301"}'  # raw JSON, sent as is
```

`NAME=VALUE` converts the value; `NAME:=JSON` sends the JSON untouched. Names are matched
case-insensitively, and `cf[10042]` works too. `acli-py field list -q team` shows names, ids and
types.

## Markdown in, Markdown out

Descriptions, comments, worklog notes and multi-line text fields are written in Markdown and
converted to Jira's Atlassian Document Format:

- paragraphs, with single line breaks kept
- `#` headings, `-` and `1.` lists (indent to nest), `>` quotes, `---` rules
- fenced code blocks with a language
- `**bold**`, `*italic*`, `~~strike~~`, `` `code` ``, `[links](https://…)` and bare URLs

If you already have an ADF document, pass its JSON and it is used unchanged.
`acli-py issue view` and `acli-py issue comment list` render rich text back as Markdown in the terminal.

Text can come from an option (`-d`, `-b`), a file (`-D`, `-B`), standard input (`-`), or your
editor (`--editor`, which uses `$VISUAL`, `$EDITOR` or `acli-py config set editor …`).

## Many issues from a file

```sh
acli-py issue create --template > issues.json   # an example to start from
acli-py issue create --from-json issues.json --dry-run
acli-py issue create --from-csv backlog.csv -p DEMO -y
```

A JSON file holds one issue or a list of them. A CSV file has a header row. Both understand
`project`, `type`, `summary`, `description`, `assignee`, `reporter`, `labels`, `components`,
`fixVersions`, `priority`, `parent` and `due`, plus any other field by name. Options on the
command line fill in whatever a row leaves out. An object already shaped like Jira's own
payload (`{"fields": {"project": …}}`) is sent as is.
