# Everyday helpers

A few commands for the things you do every day. Each one reads Jira through the same queries
as the rest of `acli-py`, and prints a table for people or `--output json`, `jsonl`,
`markdown` (and `csv` where it makes sense) for scripts, notes and chat.

## Standup

```sh
acli-py standup
acli-py standup --since 2026-09-28
acli-py standup --output markdown | pbcopy
```

`standup` lists the issues you changed since the last working day (Friday, on a Monday), then
your open issues, most important first, leaving out the ones you already listed. `--fields`
picks the columns, as for `issue search`. `--output jsonl` prints one issue per line with a
`list` member, `changed` or `next`.

## Sprint report

```sh
acli-py sprint report            # the active sprint on your default board
acli-py sprint report --board 7
acli-py sprint report 42 --output markdown
```

The report shows the sprint, its dates and goal, how many of its issues are done, then its
issues counted by status (in board order: To Do, In Progress, Done) and by assignee, busiest
first. `--json` has everything; `--output jsonl` prints one line per assignee.

## Branches and commit messages

```sh
git switch -c "$(acli-py git branch DEMO-1)"       # fix/DEMO-1-login-fails-on-safari
git commit -m "$(acli-py git commit-msg DEMO-1)"   # fix: login fails on Safari (DEMO-1)
```

Bugs (and other defect types) become `fix`, everything else `feat`. `git branch --prefix
docs/` picks another prefix, and `--prefix ''` none. `--output json` prints both names.

## Aliases

```sh
acli-py alias set mine '@me is:open sort:-priority'
acli-py alias set board-7 sprint report --board 7
acli-py alias list
```

Then run them as `acli-py @mine` or `acli-py @board-7`. Words after an alias are added to what
it runs, so `@mine --fields key,due --output keys` works.

An alias is either:

- **a query**, run by `issue search`. These are the same saved views the TUI lists, so a
  view saved in the TUI is an alias too, and so are the built-in views (those with spaces in
  their names need quotes);
- **a command line**, when the value starts with a command (`issue`, `sprint`, `standup`…).

Aliases are kept in `views.json` next to the config. In the shell, `@` and Tab complete their
names. `acli-py alias delete NAME` forgets one; the built-in views stay.
