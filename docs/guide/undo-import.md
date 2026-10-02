# Undo and import

Every change `acli-py` makes is kept in an audit log (`audit.jsonl` in the config directory,
one line per command or bulk run). `acli-py log` lists it, `acli-py undo` reverses it, and
`acli-py issue import` applies a whole file of changes as one run you can undo.

## The log

```sh
acli-py log            # the last 20 changes, newest first
acli-py log --all --json
```

Each change has an id (its line in the log), the command, the issues it touched, how many
failed, and whether it was undone. Dry runs change nothing, so they aren't logged.

## Undo

```sh
acli-py undo           # the last change not undone yet
acli-py undo 12        # a given one
acli-py undo --dry-run # what it would send
```

Undo puts back what a change replaced, from the values the log kept:

- **field edits** (`issue edit`, label changes, imports) set each field back;
- **assignments** go back to who had the issue, or to nobody;
- **transitions** move the issue back to the status it came from. When the workflow has no
  transition leading back, the issue is reported as not undone.

Before asking, undo shows each issue's value now and after. An issue that changed again since
is flagged `(changed since)`: undoing sets it back anyway, so look first. Issues already as
they were are skipped. Creating, deleting, comments and other changes can't be undone this way.

The undo is a change of its own, recorded with the id it reverses. Running `undo` again
reverses the change before it, not the undo. To redo, undo the undo by its id.

In the TUI, the activity log (`L`) undoes the last change with `u`.

## Import

```sh
acli-py issue search 'p:DEMO is:open' --fields key,summary,priority,labels --csv > open.csv
# … edit open.csv …
acli-py issue import open.csv --dry-run
acli-py issue import open.csv
```

`issue import` reads CSV with a header row, JSON (an object, a list), or JSON lines. Each row
with a `key` updates that issue; a row without one creates an issue, in its `project` column
or `--project`, of its `type` or `--type`.

Columns are the names `issue search --fields` uses (`summary`, `priority`, `assignee`,
`labels`, `components`, `fixVersions`, `parent`, `due`, `description`) or any field's name or
id (`Story point estimate`, `customfield_10016`). Values from JSON exports work too: a person,
an issue or an option is read by its id or name. `status`, `created`, `updated` and
`resolution` are skipped, since only a transition changes them. A column that matches no
field stops the import before anything is sent.

The import first shows which field each column fills. Then it compares each row with its issue
and leaves out rows that already match, so an export → edit → import round trip only changes
what you edited. It asks once, with each row's value now and after, then runs a few rows at a
time (`--concurrency`), reporting each. Rows it can't use, such as an issue that isn't there
or a person nobody matches, are listed and the exit code is 1.

The whole import is one entry in the log. `acli-py undo` puts its edits back; issues it created
stay.
